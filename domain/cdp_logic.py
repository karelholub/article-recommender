from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from domain.common import normalize_string_list, safe_parse_timestamp

MEIRO_PROVIDER = 'meiro'
DEFAULT_MEIRO_MAPPING: Dict[str, Any] = {
    'external_id_path': 'customer_entity_id',
    'traits_path': 'returned_attributes',
    'segments_path': '',
    'fixed_segments': [],
    'preferred_sources_trait': 'preferred_sources',
    'excluded_sources_trait': 'excluded_sources',
    'source_weights_trait': 'source_weights',
    'source_weight_trait_prefix': 'source_weight_',
    'scenario_segment_map': {},
    'config_segment_map': {},
    'segment_priority': [],
    'derivation_min_source_events': 3,
    'derivation_min_category_events': 1,
    'derivation_allowed_sources': [],
    'derivation_blocked_sources': [],
    'derivation_max_preferred_sources': 5,
    'derivation_min_source_weight': 1.05,
    'derivation_max_source_weight': 2.0,
    'personalization_mode': 'active',
    'fallback_mode': 'source_defaults',
    'freshness_sla_hours': 24,
}
MEIRO_MAPPING_PRESETS: Dict[str, Dict[str, Any]] = {
    'news_basic': {
        'label': 'News Basic',
        'mapping': {
            'external_id_path': 'customer_entity_id',
            'traits_path': 'returned_attributes',
            'segments_path': '',
            'preferred_sources_trait': 'preferred_sources',
            'excluded_sources_trait': 'excluded_sources',
            'source_weights_trait': 'source_weights',
            'source_weight_trait_prefix': 'source_weight_',
            'personalization_mode': 'active',
            'fallback_mode': 'source_defaults',
            'freshness_sla_hours': 24,
        },
    },
    'news_segments_first': {
        'label': 'News Segments First',
        'mapping': {
            'external_id_path': 'customer_entity_id',
            'traits_path': 'returned_attributes',
            'segments_path': 'returned_attributes.mx_predicted_lifestyle_interests',
            'segment_priority': ['premium', 'sports', 'business', 'technology'],
            'scenario_segment_map': {'premium': 'homepage_premium'},
            'config_segment_map': {'sports': 'topic_heavy', 'business': 'balanced'},
            'personalization_mode': 'observe',
            'fallback_mode': 'source_defaults',
            'freshness_sla_hours': 12,
        },
    },
}


def normalize_meiro_mapping(mapping: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(DEFAULT_MEIRO_MAPPING)
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            merged[str(key)] = value
    for key in (
        'external_id_path',
        'traits_path',
        'segments_path',
        'preferred_sources_trait',
        'excluded_sources_trait',
        'source_weights_trait',
        'source_weight_trait_prefix',
    ):
        merged[key] = str(merged.get(key, '')).strip()
    if not isinstance(merged.get('scenario_segment_map'), dict):
        merged['scenario_segment_map'] = {}
    if not isinstance(merged.get('config_segment_map'), dict):
        merged['config_segment_map'] = {}
    if not isinstance(merged.get('fixed_segments'), list):
        merged['fixed_segments'] = []
    if not isinstance(merged.get('segment_priority'), list):
        merged['segment_priority'] = []
    if not isinstance(merged.get('derivation_allowed_sources'), list):
        merged['derivation_allowed_sources'] = []
    if not isinstance(merged.get('derivation_blocked_sources'), list):
        merged['derivation_blocked_sources'] = []
    merged['derivation_min_source_events'] = max(0, int(merged.get('derivation_min_source_events', 3)))
    merged['derivation_min_category_events'] = max(0, int(merged.get('derivation_min_category_events', 1)))
    merged['derivation_max_preferred_sources'] = max(1, int(merged.get('derivation_max_preferred_sources', 5)))
    merged['derivation_min_source_weight'] = max(0.0, float(merged.get('derivation_min_source_weight', 1.05)))
    merged['derivation_max_source_weight'] = max(
        merged['derivation_min_source_weight'],
        float(merged.get('derivation_max_source_weight', 2.0)),
    )
    personalization_mode = str(merged.get('personalization_mode', 'active')).strip().lower()
    if personalization_mode not in {'off', 'observe', 'active'}:
        personalization_mode = 'active'
    fallback_mode = str(merged.get('fallback_mode', 'source_defaults')).strip().lower()
    if fallback_mode not in {'none', 'source_defaults', 'profile_traits'}:
        fallback_mode = 'source_defaults'
    merged['personalization_mode'] = personalization_mode
    merged['fallback_mode'] = fallback_mode
    merged['freshness_sla_hours'] = max(1, min(24 * 30, int(merged.get('freshness_sla_hours', 24))))
    merged['fixed_segments'] = [str(item).strip() for item in merged['fixed_segments'] if str(item).strip()]
    merged['segment_priority'] = [str(item).strip() for item in merged['segment_priority'] if str(item).strip()]
    merged['derivation_allowed_sources'] = [
        str(item).strip().lower() for item in merged['derivation_allowed_sources'] if str(item).strip()
    ]
    merged['derivation_blocked_sources'] = [
        str(item).strip().lower() for item in merged['derivation_blocked_sources'] if str(item).strip()
    ]
    return merged


def list_from_profile_trait(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


def float_map_from_profile_trait(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, float] = {}
    for key, raw in value.items():
        source = str(key).strip()
        if not source:
            continue
        try:
            out[source] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def safe_json_list_item(value: str) -> Optional[List[Any]]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else None
    except Exception:
        return None


def derive_reco_fields_from_meiro_traits(traits: Dict[str, Any]) -> Dict[str, Any]:
    source_counter: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    brands: Dict[str, int] = {}

    for key in ('web_all_products_viewed_3', 'me_shit_product_viewed_last_session2', 'web_all_purchases_comp'):
        values = traits.get(key) or []
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, str):
                continue
            row = safe_json_list_item(raw)
            if not row:
                continue
            if len(row) >= 7:
                url_candidate = str(row[6] or '').strip()
                if url_candidate:
                    parsed = urlparse(url_candidate)
                    domain = parsed.netloc.strip().lower()
                    if domain:
                        source_counter[domain] = source_counter.get(domain, 0) + 1
            if len(row) >= 5:
                category = str(row[4] or '').strip().lower()
                if category:
                    categories[category] = categories.get(category, 0) + 1
            if len(row) >= 6:
                brand = str(row[5] or '').strip().lower()
                if brand:
                    brands[brand] = brands.get(brand, 0) + 1

    preferred_sources = [item[0] for item in sorted(source_counter.items(), key=lambda x: x[1], reverse=True)[:5]]
    source_weights: Dict[str, float] = {}
    if source_counter:
        max_count = max(source_counter.values())
        for source, count in source_counter.items():
            ratio = (count / max_count) if max_count else 0.0
            source_weights[source] = round(1.0 + ratio, 3)

    segments = []
    rfm_values = traits.get('web_rfm') or []
    if isinstance(rfm_values, list):
        for value in rfm_values:
            text = str(value).strip().lower()
            if text:
                segments.append(f"rfm:{text.replace(' ', '_')}")
    lifestage = traits.get('mx_predicted_lifestage') or []
    if isinstance(lifestage, list):
        for value in lifestage:
            text = str(value).strip().lower()
            if text:
                segments.append(f"lifestage:{text.replace(' ', '_')}")
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]:
        if count > 0:
            segments.append(f"cat:{category}")
    for brand, count in sorted(brands.items(), key=lambda x: x[1], reverse=True)[:2]:
        if count > 0:
            segments.append(f"brand:{brand.replace(' ', '_')}")
    segments = sorted(set(segments))

    return {
        'preferred_sources': preferred_sources,
        'source_weights': source_weights,
        'derived_segments': segments,
        'top_categories': [item[0] for item in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]],
        'top_brands': [item[0] for item in sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]],
        'support': {
            'source_events': sum(source_counter.values()),
            'category_events': sum(categories.values()),
            'brand_events': sum(brands.values()),
        },
    }


def apply_derivation_guardrails(derived: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
    support = derived.get('support') or {}
    source_events = int(support.get('source_events') or 0)
    category_events = int(support.get('category_events') or 0)
    min_source_events = int(mapping.get('derivation_min_source_events', 3))
    min_category_events = int(mapping.get('derivation_min_category_events', 1))
    allowed = set(str(item).strip().lower() for item in (mapping.get('derivation_allowed_sources') or []) if str(item).strip())
    blocked = set(str(item).strip().lower() for item in (mapping.get('derivation_blocked_sources') or []) if str(item).strip())
    max_sources = int(mapping.get('derivation_max_preferred_sources', 5))
    min_weight = float(mapping.get('derivation_min_source_weight', 1.05))
    max_weight = float(mapping.get('derivation_max_source_weight', 2.0))

    reasons = []
    if source_events < min_source_events:
        reasons.append(f'insufficient_source_events:{source_events}<{min_source_events}')
    if category_events < min_category_events:
        reasons.append(f'insufficient_category_events:{category_events}<{min_category_events}')

    preferred = [str(item).strip().lower() for item in (derived.get('preferred_sources') or []) if str(item).strip()]
    weights = dict(derived.get('source_weights') or {})
    filtered = []
    dropped_by_policy = []
    for source in preferred:
        if allowed and source not in allowed:
            dropped_by_policy.append({'source': source, 'reason': 'not_in_allowlist'})
            continue
        if source in blocked:
            dropped_by_policy.append({'source': source, 'reason': 'in_blocklist'})
            continue
        filtered.append(source)
    filtered = filtered[:max_sources]

    final_weights: Dict[str, float] = {}
    for source in filtered:
        raw = weights.get(source, 1.0)
        try:
            weight = float(raw)
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(min_weight, min(max_weight, weight))
        final_weights[source] = round(weight, 3)

    if not filtered:
        reasons.append('no_preferred_sources_after_policy')

    guardrail_pass = len(reasons) == 0
    return {
        'pass': guardrail_pass,
        'reasons': reasons,
        'policy': {
            'min_source_events': min_source_events,
            'min_category_events': min_category_events,
            'allowlist_size': len(allowed),
            'blocklist_size': len(blocked),
            'max_preferred_sources': max_sources,
            'min_source_weight': min_weight,
            'max_source_weight': max_weight,
        },
        'dropped_sources': dropped_by_policy,
        'result': {
            'preferred_sources': filtered,
            'source_weights': final_weights,
            'derived_segments': list(derived.get('derived_segments') or []),
            'top_categories': list(derived.get('top_categories') or []),
            'top_brands': list(derived.get('top_brands') or []),
            'support': support,
        },
    }


def build_derivation_diff(profile: Dict[str, Any], guarded: Dict[str, Any]) -> Dict[str, Any]:
    current_traits = dict(profile.get('traits') or {})
    current_segments = [str(item).strip() for item in (profile.get('segments') or []) if str(item).strip()]
    result = guarded.get('result') or {}
    next_preferred = list(result.get('preferred_sources') or [])
    next_weights = dict(result.get('source_weights') or {})
    next_segments = sorted(set(current_segments + list(result.get('derived_segments') or [])))

    current_preferred = [str(item).strip().lower() for item in list_from_profile_trait(current_traits.get('preferred_sources'))]
    current_weights = float_map_from_profile_trait(current_traits.get('source_weights'))
    added_segments = [item for item in next_segments if item not in current_segments]

    return {
        'preferred_sources': {
            'before': current_preferred,
            'after': next_preferred,
            'added': [item for item in next_preferred if item not in current_preferred],
            'removed': [item for item in current_preferred if item not in next_preferred],
            'changed': current_preferred != next_preferred,
        },
        'source_weights': {
            'before': current_weights,
            'after': next_weights,
            'changed_keys': sorted(set(current_weights.keys()) ^ set(next_weights.keys()))
            + sorted(
                key
                for key in set(current_weights.keys()) & set(next_weights.keys())
                if abs(float(current_weights.get(key, 0.0)) - float(next_weights.get(key, 0.0))) > 1e-9
            ),
            'changed': current_weights != next_weights,
        },
        'segments': {
            'before': current_segments,
            'after': next_segments,
            'added': added_segments,
            'changed': bool(added_segments),
        },
        'has_changes': (current_preferred != next_preferred or current_weights != next_weights or bool(added_segments)),
    }


def resolve_cdp_personalization(
    store: Any,
    external_user_id: Optional[str],
    requested_sources: List[str],
    scenario_id: Optional[str],
    config_id: str,
    scenario_explicit: bool,
    config_explicit: bool,
    provider: str = MEIRO_PROVIDER,
) -> Dict[str, Any]:
    external = str(external_user_id or '').strip()
    base = {
        'applied': False,
        'provider': provider,
        'external_user_id': external or None,
        'profile_found': False,
        'segments': [],
        'preferred_sources': [],
        'excluded_sources': [],
        'source_weight_overrides': {},
        'selected_scenario_id': scenario_id,
        'selected_config_id': config_id,
        'requested_sources': list(requested_sources or []),
        'mapping': DEFAULT_MEIRO_MAPPING,
        'personalization_mode': 'active',
        'fallback_mode': 'source_defaults',
        'profile_stale': None,
        'profile_age_hours': None,
    }
    if not store:
        return base
    integration = store.get_cdp_integration(provider)
    mapping = normalize_meiro_mapping(integration.get('mapping'))
    base['mapping'] = mapping
    base['personalization_mode'] = mapping.get('personalization_mode', 'active')
    base['fallback_mode'] = mapping.get('fallback_mode', 'source_defaults')
    if not integration.get('enabled'):
        return base
    if mapping.get('personalization_mode') == 'off':
        base['applied_mode'] = 'off'
        return base
    if not external:
        return base
    profile = store.get_cdp_profile(provider, external)
    if not profile:
        base['applied_mode'] = 'no_profile'
        return base
    base['profile_found'] = True
    synced_at = safe_parse_timestamp(str(profile.get('synced_at', '')))
    profile_age_hours = None
    profile_stale = None
    if synced_at:
        profile_age_hours = round((datetime.now() - synced_at).total_seconds() / 3600, 3)
        profile_stale = profile_age_hours > float(mapping.get('freshness_sla_hours', 24))
    base['profile_age_hours'] = profile_age_hours
    base['profile_stale'] = profile_stale
    traits = profile.get('traits') or {}
    if not isinstance(traits, dict):
        traits = {}
    segments = [str(item).strip() for item in (profile.get('segments') or []) if str(item).strip()]
    base['segments'] = segments

    preferred_sources = list_from_profile_trait(traits.get(mapping.get('preferred_sources_trait')))
    excluded_sources = list_from_profile_trait(traits.get(mapping.get('excluded_sources_trait')))
    source_weight_overrides = float_map_from_profile_trait(traits.get(mapping.get('source_weights_trait')))
    prefix = mapping.get('source_weight_trait_prefix')
    if prefix:
        for key, value in traits.items():
            trait_key = str(key)
            if not trait_key.startswith(prefix):
                continue
            source = trait_key[len(prefix):].strip()
            if not source:
                continue
            try:
                source_weight_overrides[source] = float(value)
            except (TypeError, ValueError):
                continue

    source_set = set(requested_sources or [])
    source_set.update(preferred_sources)
    source_set.difference_update(excluded_sources)
    merged_sources = sorted(source_set)

    scenario_segment_map = {str(k): str(v).strip() for k, v in (mapping.get('scenario_segment_map') or {}).items() if str(v).strip()}
    config_segment_map = {str(k): str(v).strip() for k, v in (mapping.get('config_segment_map') or {}).items() if str(v).strip()}
    segment_priority = mapping.get('segment_priority') or []
    segment_order = segment_priority + [seg for seg in segments if seg not in segment_priority]

    selected_scenario_id = scenario_id
    if not scenario_explicit and not selected_scenario_id:
        for segment in segment_order:
            candidate = scenario_segment_map.get(segment)
            if candidate:
                selected_scenario_id = candidate
                break

    selected_config_id = config_id
    if not config_explicit:
        for segment in segment_order:
            candidate = config_segment_map.get(segment)
            if candidate:
                selected_config_id = candidate
                break

    allow_apply = mapping.get('personalization_mode') == 'active' and (
        profile_stale is not True or mapping.get('fallback_mode') == 'profile_traits'
    )
    if mapping.get('personalization_mode') == 'observe':
        allow_apply = False

    base.update(
        {
            'applied': bool(profile),
            'preferred_sources': preferred_sources,
            'excluded_sources': excluded_sources,
            'source_weight_overrides': source_weight_overrides if allow_apply else {},
            'selected_scenario_id': selected_scenario_id if allow_apply else scenario_id,
            'selected_config_id': selected_config_id if allow_apply else config_id,
            'requested_sources': (merged_sources if allow_apply else list(requested_sources or [])),
            'profile_synced_at': profile.get('synced_at'),
            'applied_mode': (mapping.get('personalization_mode') if allow_apply else f"{mapping.get('personalization_mode')}_no_apply"),
        }
    )
    return base


def resolve_experiment_assignment(experiment: Optional[Dict[str, Any]], effective_user_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(experiment, dict):
        return None
    experiment_id = str(experiment.get('experiment_id', '')).strip()
    variants = experiment.get('variants') or []
    if not experiment_id or not isinstance(variants, list) or not variants:
        return None

    normalized = []
    total_weight = 0.0
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_id = str(variant.get('variant_id', '')).strip()
        weight = float(variant.get('weight', 0.0))
        if not variant_id or weight <= 0:
            continue
        normalized.append(
            {
                'variant_id': variant_id,
                'weight': weight,
                'config_id': str(variant.get('config_id', '')).strip() or None,
                'scenario_id': str(variant.get('scenario_id', '')).strip() or None,
                'source_overrides': normalize_string_list(variant.get('sources')),
            }
        )
        total_weight += weight
    if not normalized or total_weight <= 0:
        return None

    token = f'{experiment_id}:{effective_user_id}'
    bucket = int(hashlib.sha1(token.encode('utf-8')).hexdigest()[:8], 16) / 0xFFFFFFFF
    cursor = 0.0
    selected = normalized[-1]
    for candidate in normalized:
        cursor += candidate['weight'] / total_weight
        if bucket <= cursor:
            selected = candidate
            break
    return {
        'experiment_id': experiment_id,
        'variant_id': selected['variant_id'],
        'bucket': round(bucket, 6),
        'selected_config_id': selected['config_id'],
        'selected_scenario_id': selected['scenario_id'],
        'selected_sources': selected['source_overrides'],
        'variants_total': len(normalized),
    }
