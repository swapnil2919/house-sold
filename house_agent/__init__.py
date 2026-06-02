"""House-Sold: a 99acres-style property agent powered by the NRE kernel.

`engine` is imported lazily so the tool layer (search/pricing/locality) can be
used without the NRE package installed.
"""

__all__ = ["build_house_agent_engine", "run_turn"]


def __getattr__(name):
    if name in {"build_house_agent_engine", "run_turn"}:
        from house_agent import engine  # noqa: WPS433
        return getattr(engine, name)
    raise AttributeError(name)
