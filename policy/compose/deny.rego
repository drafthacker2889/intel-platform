package main

stateful_services := {"elasticsearch", "redis", "neo4j", "collector-go", "sanitizer-rust", "brain-python", "dashboard-ui", "gateway"}

warn[msg] if {
  some name
  service := input.services[name]
  service.image
  endswith(service.image, ":latest")
  msg := sprintf("service %s must not use latest tag", [name])
}

deny[msg] if {
  some name
  stateful_services[name]
  not input.services[name].restart
  msg := sprintf("service %s must declare a restart policy", [name])
}

deny[msg] if {
  some name
  required := {"elasticsearch", "redis", "neo4j"}
  required[name]
  not input.services[name].healthcheck
  msg := sprintf("service %s must declare a healthcheck", [name])
}

deny[msg] if {
  count(input.services.gateway.ports) == 0
  msg := "gateway must expose a host port"
}
