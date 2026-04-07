package terraform

# Deny security groups with 0.0.0.0/0 ingress
deny[msg] if {
    some resource
    input.resource.aws_security_group[resource]
    some rule
    ingress := input.resource.aws_security_group[resource].ingress[rule]
    some cidr
    ingress.cidr_blocks[cidr] == "0.0.0.0/0"
    msg := sprintf("security group %s allows unrestricted ingress (0.0.0.0/0)", [resource])
}

# Deny unencrypted S3 buckets
deny[msg] if {
    some bucket
    input.resource.aws_s3_bucket[bucket]
    not _has_encryption(bucket)
    msg := sprintf("S3 bucket %s must enable server-side encryption", [bucket])
}

_has_encryption(bucket) if {
    input.resource.aws_s3_bucket_server_side_encryption_configuration[_].bucket == bucket
}

_has_encryption(bucket) if {
    input.resource.aws_s3_bucket[bucket].server_side_encryption_configuration
}

# Deny public RDS instances
deny[msg] if {
    some db
    input.resource.aws_db_instance[db]
    input.resource.aws_db_instance[db].publicly_accessible == true
    msg := sprintf("RDS instance %s must not be publicly accessible", [db])
}

# Deny unencrypted RDS instances
deny[msg] if {
    some db
    input.resource.aws_db_instance[db]
    not input.resource.aws_db_instance[db].storage_encrypted
    msg := sprintf("RDS instance %s must enable storage encryption", [db])
}

# Deny ElastiCache without auth
deny[msg] if {
    some cluster
    input.resource.aws_elasticache_replication_group[cluster]
    not input.resource.aws_elasticache_replication_group[cluster].auth_token
    msg := sprintf("ElastiCache cluster %s must set auth_token", [cluster])
}

# Deny Elasticsearch domains without encryption at rest
deny[msg] if {
    some domain
    input.resource.aws_elasticsearch_domain[domain]
    not input.resource.aws_elasticsearch_domain[domain].encrypt_at_rest
    msg := sprintf("Elasticsearch domain %s must enable encrypt_at_rest", [domain])
}

# Warn on missing tags
warn[msg] if {
    some resource_type
    some name
    resource := input.resource[resource_type][name]
    not resource.tags
    msg := sprintf("%s.%s should have tags for cost allocation and ownership", [resource_type, name])
}

# Deny IAM policies with wildcard actions
deny[msg] if {
    some policy
    input.resource.aws_iam_policy[policy]
    some stmt
    statement := input.resource.aws_iam_policy[policy].policy.Statement[stmt]
    statement.Effect == "Allow"
    some action
    statement.Action[action] == "*"
    msg := sprintf("IAM policy %s must not use wildcard (*) actions", [policy])
}
