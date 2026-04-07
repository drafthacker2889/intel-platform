package kubernetes

# Deny containers running as root
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.securityContext.runAsNonRoot
    msg := sprintf("container %s must set securityContext.runAsNonRoot: true", [container.name])
}

# Deny missing resource limits
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.resources.limits
    msg := sprintf("container %s must declare resource limits", [container.name])
}

# Deny missing liveness probe
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.livenessProbe
    msg := sprintf("container %s must declare a livenessProbe", [container.name])
}

# Deny missing readiness probe
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.readinessProbe
    msg := sprintf("container %s must declare a readinessProbe", [container.name])
}

# Deny privileged containers
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    container.securityContext.privileged
    msg := sprintf("container %s must not be privileged", [container.name])
}

# Deny latest tag in images
deny[msg] if {
    some container
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    endswith(container.image, ":latest")
    msg := sprintf("container %s must not use :latest tag", [container.name])
}

# Deny missing namespace
deny[msg] if {
    input.kind == "Deployment"
    not input.metadata.namespace
    msg := "deployment must specify a namespace"
}

# Warn on missing pod disruption budget
warn[msg] if {
    input.kind == "Deployment"
    input.spec.replicas > 1
    msg := sprintf("deployment %s has multiple replicas but no PodDisruptionBudget referenced", [input.metadata.name])
}
