class Const:
    SUPPORTED_CONDITION_TYPES = ['public', 'fail_gate', 'pass_gate', 'ip_based', 'ua_based', 'user_field',
                                 'environment_field', 'current_time', 'user_bucket', 'unit_id', 'multi_pass_gate',
                                 'multi_fail_gate']

    SUPPORTED_OPERATORS = ['gt', 'gte', 'lt', 'lte',
                           'version_gt', 'version_gte', 'version_lt', 'version_lte',
                           'version_eq', 'version_neq',
                           'any', 'none', 'any_case_sensitive', 'none_case_sensitive',
                           'str_starts_with_any', 'str_ends_with_any', 'str_contains_any', 'str_contains_none',
                           'str_matches', 'eq', 'neq', 'before', 'after', 'on',
                           'in_segment_list', 'not_in_segment_list']
