"""
Seed Junction A with default config and 4 signal heads (NORTH, SOUTH, EAST, WEST).

Idempotent: running it again is safe and updates the config to defaults.

Usage:
    cd backend
    python -m scripts.seed_junction_a
"""
from app.db import SessionLocal
from app.models import Junction, JunctionConfig, Signal


def main() -> None:
    with SessionLocal() as db:
        junction = db.get(Junction, "A")
        if junction is None:
            junction = Junction(id="A", name="Main Junction")
            db.add(junction)
        else:
            junction.name = "Main Junction"

        config = db.get(JunctionConfig, "A")
        if config is None:
            config = JunctionConfig(
                junction_id="A",
                green_duration_sec=30,
                yellow_duration_sec=5,
                all_red_duration_sec=2,
                min_green_sec=10,
                starvation_threshold_sec=60,
                phases_json=[["NORTH", "SOUTH"], ["EAST", "WEST"]],
            )
            db.add(config)
        else:
            config.green_duration_sec = 30
            config.yellow_duration_sec = 5
            config.all_red_duration_sec = 2
            config.min_green_sec = 10
            config.starvation_threshold_sec = 60
            config.phases_json = [["NORTH", "SOUTH"], ["EAST", "WEST"]]

        for d in ("NORTH", "SOUTH", "EAST", "WEST"):
            existing = (db.query(Signal)
                          .filter_by(junction_id="A", direction=d)
                          .one_or_none())
            if existing is None:
                db.add(Signal(junction_id="A", direction=d))

        db.commit()
        print("Junction A seeded.")


if __name__ == "__main__":
    main()
