from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from domain.common import extract_sections, normalize_string_list, safe_article_age_days


def validate_scenario_rule_set(rule_set: Dict[str, Any]) -> Dict[str, Any]:
    candidate = dict(rule_set or {})
    normalized = {
        'include_sources': normalize_string_list(candidate.get('include_sources')),
        'exclude_sources': normalize_string_list(candidate.get('exclude_sources')),
        'include_sections': [value.lower() for value in normalize_string_list(candidate.get('include_sections'))],
        'exclude_sections': [value.lower() for value in normalize_string_list(candidate.get('exclude_sections'))],
        'include_keywords': [value.lower() for value in normalize_string_list(candidate.get('include_keywords'))],
        'exclude_keywords': [value.lower() for value in normalize_string_list(candidate.get('exclude_keywords'))],
        'exclude_article_ids': normalize_string_list(candidate.get('exclude_article_ids')),
        'max_age_days': candidate.get('max_age_days'),
        'min_score': candidate.get('min_score'),
        'source_boosts': {str(key): float(value) for key, value in (candidate.get('source_boosts') or {}).items()},
        'ranking_config_id': str(candidate.get('ranking_config_id', '')).strip() or None,
        'max_per_source': candidate.get('max_per_source'),
        'max_per_topic': candidate.get('max_per_topic'),
        'max_per_section': candidate.get('max_per_section'),
        'min_freshness': candidate.get('min_freshness'),
        'recent_boost_days': candidate.get('recent_boost_days'),
        'recent_boost_factor': candidate.get('recent_boost_factor'),
        'dedup_by_title': bool(candidate.get('dedup_by_title', False)),
        'dedup_by_url': bool(candidate.get('dedup_by_url', False)),
    }

    if normalized['max_age_days'] is not None:
        normalized['max_age_days'] = max(0, int(normalized['max_age_days']))
    if normalized['min_score'] is not None:
        normalized['min_score'] = float(normalized['min_score'])
    for source, boost in normalized['source_boosts'].items():
        if boost <= 0:
            raise ValueError(f'source_boosts[{source}] must be greater than 0')
    for key in ('max_per_source', 'max_per_topic', 'max_per_section'):
        if normalized.get(key) is not None:
            normalized[key] = max(1, int(normalized[key]))
    if normalized.get('min_freshness') is not None:
        normalized['min_freshness'] = float(normalized['min_freshness'])
        if normalized['min_freshness'] < 0 or normalized['min_freshness'] > 1:
            raise ValueError('min_freshness must be between 0 and 1')
    if normalized.get('recent_boost_days') is not None:
        normalized['recent_boost_days'] = max(0, int(normalized['recent_boost_days']))
    else:
        normalized['recent_boost_days'] = 0
    if normalized.get('recent_boost_factor') is not None:
        normalized['recent_boost_factor'] = float(normalized['recent_boost_factor'])
    else:
        normalized['recent_boost_factor'] = 1.0
    if normalized['recent_boost_factor'] < 0.5 or normalized['recent_boost_factor'] > 5:
        raise ValueError('recent_boost_factor must be between 0.5 and 5')

    return normalized


def apply_scenario_rules(
    recommendations: list,
    scenario: Optional[Dict[str, Any]],
    recommender: Any,
    include_decisions: bool = False,
) -> Tuple[list, Dict[str, Any]]:
    if not scenario:
        trace = {'applied': False, 'scenario_id': None, 'filtered_out': 0, 'reasons': {}}
        if include_decisions:
            trace['decisions'] = []
        return recommendations, trace

    rule_set = scenario.get('rule_set') or {}
    include_sources = set(normalize_string_list(rule_set.get('include_sources')))
    exclude_sources = set(normalize_string_list(rule_set.get('exclude_sources')))
    include_sections = set(value.lower() for value in normalize_string_list(rule_set.get('include_sections')))
    exclude_sections = set(value.lower() for value in normalize_string_list(rule_set.get('exclude_sections')))
    include_keywords = [value.lower() for value in normalize_string_list(rule_set.get('include_keywords'))]
    exclude_keywords = [value.lower() for value in normalize_string_list(rule_set.get('exclude_keywords'))]
    exclude_article_ids = set(normalize_string_list(rule_set.get('exclude_article_ids')))
    source_boosts = {key: float(value) for key, value in (rule_set.get('source_boosts') or {}).items()}
    max_age_days = rule_set.get('max_age_days')
    min_score = rule_set.get('min_score')
    min_freshness = rule_set.get('min_freshness')
    max_per_source = rule_set.get('max_per_source')
    max_per_topic = rule_set.get('max_per_topic')
    max_per_section = rule_set.get('max_per_section')
    recent_boost_days = rule_set.get('recent_boost_days')
    recent_boost_factor = rule_set.get('recent_boost_factor')
    dedup_by_title = bool(rule_set.get('dedup_by_title', False))
    dedup_by_url = bool(rule_set.get('dedup_by_url', False))
    if max_age_days is not None:
        max_age_days = max(0, int(max_age_days))
    if min_score is not None:
        min_score = float(min_score)
    if min_freshness is not None:
        min_freshness = float(min_freshness)
    if max_per_source is not None:
        max_per_source = max(1, int(max_per_source))
    if max_per_topic is not None:
        max_per_topic = max(1, int(max_per_topic))
    if max_per_section is not None:
        max_per_section = max(1, int(max_per_section))
    recent_boost_days = max(0, int(recent_boost_days or 0))
    recent_boost_factor = float(recent_boost_factor or 1.0)

    kept = []
    filtered = 0
    reasons: Dict[str, int] = {}
    decisions = []
    source_counts: Dict[str, int] = {}
    topic_counts: Dict[str, int] = {}
    section_counts: Dict[str, int] = {}
    seen_titles: set = set()
    seen_urls: set = set()

    for rec in recommendations:
        article_id = rec.get('article_id')
        article_meta = recommender.article_vectors.get(article_id, {}).get('metadata', {})
        source = rec.get('source', 'unknown')
        title = str(article_meta.get('title', rec.get('title', ''))).lower()
        content = str(article_meta.get('content', rec.get('content', ''))).lower()
        url = str(article_meta.get('url', rec.get('url', '')))
        sections = extract_sections(article_meta, url)
        section_primary = sections[0] if sections else 'unknown'
        topic_cluster = str(rec.get('topic_cluster', 'unknown'))
        scraped_at = str(article_meta.get('scraped_at', ''))
        age_days = safe_article_age_days(scraped_at)
        freshness_score = float((rec.get('features') or {}).get('freshness', rec.get('similarity_components', {}).get('freshness', 1.0)))
        title_key = str(article_meta.get('title', rec.get('title', ''))).strip().lower()
        url_key = url.strip().lower()

        deny_reason = None
        if include_sources and source not in include_sources:
            deny_reason = 'source_not_included'
        elif source in exclude_sources:
            deny_reason = 'source_excluded'
        elif include_sections and not any(section in include_sections for section in sections):
            deny_reason = 'section_not_included'
        elif exclude_sections and any(section in exclude_sections for section in sections):
            deny_reason = 'section_excluded'
        elif exclude_article_ids and article_id in exclude_article_ids:
            deny_reason = 'article_excluded'
        elif include_keywords and not any(keyword in f'{title} {content}' for keyword in include_keywords):
            deny_reason = 'keyword_not_included'
        elif exclude_keywords and any(keyword in f'{title} {content}' for keyword in exclude_keywords):
            deny_reason = 'keyword_excluded'
        elif max_age_days is not None and age_days is not None and age_days > max_age_days:
            deny_reason = 'too_old'
        elif min_freshness is not None and freshness_score < min_freshness:
            deny_reason = 'below_min_freshness'
        elif min_score is not None and float(rec.get('score', 0.0)) < min_score:
            deny_reason = 'below_min_score'
        elif dedup_by_title and title_key and title_key in seen_titles:
            deny_reason = 'dedup_title'
        elif dedup_by_url and url_key and url_key in seen_urls:
            deny_reason = 'dedup_url'
        elif max_per_source is not None and source_counts.get(source, 0) >= max_per_source:
            deny_reason = 'cap_source'
        elif max_per_topic is not None and topic_counts.get(topic_cluster, 0) >= max_per_topic:
            deny_reason = 'cap_topic'
        elif max_per_section is not None and section_counts.get(section_primary, 0) >= max_per_section:
            deny_reason = 'cap_section'

        if deny_reason:
            filtered += 1
            reasons[deny_reason] = reasons.get(deny_reason, 0) + 1
            if include_decisions:
                decisions.append(
                    {
                        'article_id': article_id,
                        'source': source,
                        'status': 'filtered',
                        'reason': deny_reason,
                        'score_before': round(float(rec.get('score', 0.0)), 4),
                    }
                )
            continue

        boost = float(source_boosts.get(source, 1.0))
        if recent_boost_days > 0 and age_days is not None and age_days <= recent_boost_days:
            boost *= recent_boost_factor
        updated = dict(rec)
        original_score = float(updated.get('score', 0.0))
        boosted_score = original_score * boost
        updated['score_before_scenario'] = round(original_score, 4)
        updated['score'] = round(boosted_score, 4)
        updated['scenario_boost'] = round(boost, 4)
        updated['scenario_id'] = scenario['scenario_id']
        kept.append(updated)
        source_counts[source] = source_counts.get(source, 0) + 1
        topic_counts[topic_cluster] = topic_counts.get(topic_cluster, 0) + 1
        section_counts[section_primary] = section_counts.get(section_primary, 0) + 1
        if title_key:
            seen_titles.add(title_key)
        if url_key:
            seen_urls.add(url_key)
        if include_decisions:
            decisions.append(
                {
                    'article_id': article_id,
                    'source': source,
                    'status': 'kept',
                    'reason': 'passed',
                    'score_before': round(original_score, 4),
                    'score_after': round(boosted_score, 4),
                    'boost': round(boost, 4),
                }
            )

    kept.sort(key=lambda item: item.get('score', 0.0), reverse=True)
    return kept, {
        'applied': True,
        'scenario_id': scenario['scenario_id'],
        'scenario_name': scenario.get('name'),
        'filtered_out': filtered,
        'remaining': len(kept),
        'reasons': reasons,
        'decisions': decisions if include_decisions else None,
    }
