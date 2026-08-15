"""Entry point in the application"""

from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from coop_manager.base.routes import base


def check_env():
    """Checks the mandatory environment variables"""

    mand_env_vars: list[str] = [
        'SECRET_KEY',
    ]

    for env_var in mand_env_vars:
        if getenv(env_var) is None:
            raise ValueError(f"Environment Variable '{env_var}' is not set")


def check_and_create_folder_struct(app: Flask):
    """Checks if all mandatory folders are existent and creates them if not"""
    mand_folders = [
        'data',
        'logs'
    ]

    for folder in mand_folders:
        full_path = Path(app.root_path).parent.parent / folder
        full_path.mkdir(parents=True, exist_ok=True)


def create_app():
    """Creates the app object. Entry function for WSGI server"""
    load_dotenv()
    check_env()

    app = Flask(__name__)
    check_and_create_folder_struct(app)

    app.config['SECRET_KEY'] = getenv('SECRET_KEY')
    db_path = Path(app.root_path).parent.parent / 'data' / 'event_store.sqlite'
    db_path.touch(exist_ok=True)
    app.config['DATABASE_URL'] = db_path

    app.register_blueprint(base)
    return app


# app = create_app()


def main():
    """Entry for the development server"""
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=5555,
        debug=True
    )


if __name__ == '__main__':
    main()
