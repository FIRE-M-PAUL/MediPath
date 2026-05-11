try:
    from backend.app import app, db
    from backend.relational_schema import init_relational_schema
except ModuleNotFoundError:
    from app import app, db
    from relational_schema import init_relational_schema


def main():
    with app.app_context():
        db.create_all()
        init_relational_schema()
        print("Relational schema initialized successfully.")


if __name__ == '__main__':
    main()
