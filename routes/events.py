from __future__ import annotations

import traceback

from flask import Blueprint, current_app, jsonify, request

events_blueprint = Blueprint('events_blueprint', __name__)


def _store():
    return current_app.config.get('APP_STORE')


def _logger():
    return current_app.config['APP_LOGGER']


def _helpers():
    return current_app.config['APP_HELPERS']


@events_blueprint.route('/api/events', methods=['GET', 'POST'])
@events_blueprint.route('/api/v1/events', methods=['GET', 'POST'])
def recommendation_events():
    if not _store():
        return jsonify({'error': 'Store unavailable'}), 500

    if request.method == 'GET':
        try:
            limit = max(1, min(1000, int(request.args.get('limit', 100))))
            offset = max(0, int(request.args.get('offset', 0)))
            scenario_id = request.args.get('scenario_id')
            event_type = request.args.get('event_type')
            days = int(request.args.get('days')) if request.args.get('days') else None
            rows = _store().list_events(
                limit=limit + 1,
                offset=offset,
                scenario_id=scenario_id,
                event_type=event_type,
                days=days,
            )
            has_more = len(rows) > limit
            events = rows[:limit]
            return jsonify(
                {
                    'api_version': 'v1',
                    'events': events,
                    'count': len(events),
                    'limit': limit,
                    'offset': offset,
                    'has_more': has_more,
                    'next_offset': (offset + limit) if has_more else None,
                }
            )
        except Exception as e:
            _logger().error(f'Error listing events: {str(e)}')
            _logger().error(traceback.format_exc())
            return jsonify({'error': str(e)}), 500

    try:
        payload = request.get_json() or {}
        idempotency_key = _helpers()['read_idempotency_key'](payload)
        if idempotency_key:
            cached = _store().get_idempotency_record('events_ingest', idempotency_key)
            if cached:
                response = jsonify(cached['response'])
                response.headers['X-Idempotent-Replay'] = 'true'
                return response, int(cached['status_code'])
        raw_events = payload.get('events')
        if raw_events is None:
            raw_events = [payload]

        validated = []
        for event in raw_events:
            event_type = str(event.get('event_type', '')).strip()
            if event_type not in {'impression', 'click', 'conversion'}:
                return _helpers()['validation_error'](
                    'event_type must be one of: impression, click, conversion',
                    code='invalid_event_type',
                    details={'event_type': event_type},
                )
            user_id = str(event.get('user_id', 'anonymous')).strip() or 'anonymous'
            external_user_id = str(event.get('external_user_id', '')).strip() or None
            effective_user_id = _helpers()['resolve_effective_user_id'](user_id, external_user_id)
            validated.append(
                {
                    'event_type': event_type,
                    'run_id': event.get('run_id'),
                    'article_id': event.get('article_id'),
                    'scenario_id': event.get('scenario_id'),
                    'user_id': effective_user_id,
                    'external_user_id': external_user_id,
                    'rank_position': event.get('rank_position'),
                    'event_value': float(event.get('event_value', 1.0)),
                    'metadata': event.get('metadata') or {},
                }
            )

        inserted = _store().record_events(validated)
        response_payload = {'api_version': 'v1', 'inserted': inserted}
        if idempotency_key:
            _store().save_idempotency_record(
                endpoint='events_ingest',
                key=idempotency_key,
                status_code=201,
                response_payload=response_payload,
            )
        return jsonify(response_payload), 201
    except Exception as e:
        _logger().error(f'Error recording events: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@events_blueprint.route('/api/events/ingest-async', methods=['POST'])
@events_blueprint.route('/api/v1/events/ingest-async', methods=['POST'])
def recommendation_events_async():
    if not _store():
        return jsonify({'error': 'Store unavailable'}), 500
    try:
        payload = request.get_json() or {}
        raw_events = payload.get('events')
        if raw_events is None:
            raw_events = [payload]
        if not isinstance(raw_events, list) or not raw_events:
            return _helpers()['validation_error']('events must be a non-empty array', code='invalid_events_payload')
        if len(raw_events) > 5000:
            return _helpers()['validation_error']('Maximum async batch size is 5000', code='events_batch_too_large')

        validated = []
        for event in raw_events:
            event_type = str(event.get('event_type', '')).strip()
            if event_type not in {'impression', 'click', 'conversion'}:
                return _helpers()['validation_error'](
                    'event_type must be one of: impression, click, conversion',
                    code='invalid_event_type',
                    details={'event_type': event_type},
                )
            user_id = str(event.get('user_id', 'anonymous')).strip() or 'anonymous'
            external_user_id = str(event.get('external_user_id', '')).strip() or None
            effective_user_id = _helpers()['resolve_effective_user_id'](user_id, external_user_id)
            validated.append(
                {
                    'event_type': event_type,
                    'run_id': event.get('run_id'),
                    'article_id': event.get('article_id'),
                    'scenario_id': event.get('scenario_id'),
                    'user_id': effective_user_id,
                    'external_user_id': external_user_id,
                    'rank_position': event.get('rank_position'),
                    'event_value': float(event.get('event_value', 1.0)),
                    'metadata': event.get('metadata') or {},
                }
            )
        job = _helpers()['enqueue_event_batch'](validated, actor_id=str(payload.get('actor_id', 'system')))
        return jsonify({'api_version': 'v1', 'queued': True, 'job': job}), 202
    except Exception as e:
        _logger().error(f'Error enqueuing async events: {str(e)}')
        _logger().error(traceback.format_exc())
        return jsonify({'error': str(e)}), 400


@events_blueprint.route('/api/events/ingest-status/<job_id>', methods=['GET'])
@events_blueprint.route('/api/v1/events/ingest-status/<job_id>', methods=['GET'])
def recommendation_events_async_status(job_id):
    job = _helpers()['get_events_job'](job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    state = _helpers()['events_queue_state']()
    return jsonify({'api_version': 'v1', 'job': job, 'queue': state})


@events_blueprint.route('/api/events/ingest-queue-status', methods=['GET'])
@events_blueprint.route('/api/v1/events/ingest-queue-status', methods=['GET'])
def recommendation_events_async_queue_status():
    return jsonify({'api_version': 'v1', 'queue': _helpers()['events_queue_state']()})
