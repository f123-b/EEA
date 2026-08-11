# Built-in Domain Plugins

This directory contains official built-in Domain plugins. M14 provides the Core-neutral registry
and project activation infrastructure; M15 adds the first concrete control-domain plugin at
`plugins/builtin/motor_control/`. Additional plugins must use the same DomainPlugin contract and
must not add vertical-domain concepts to Core.
