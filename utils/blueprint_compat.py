"""Keep legacy url_for endpoints while dispatching through real blueprints."""


def register_legacy_blueprint(app, blueprint, endpoints):
    app.register_blueprint(blueprint)
    for name in endpoints:
        qualified = f"{blueprint.name}.{name}"
        if name in app.view_functions:
            raise ValueError(f"Legacy endpoint collision: {name}")
        app.view_functions[name] = app.view_functions[qualified]
        for rule in list(app.url_map.iter_rules(qualified)):
            alias = rule.empty()
            alias.endpoint = name
            alias.build_only = True
            app.url_map.add(alias)
