from flask import Flask
from dotenv import load_dotenv
from os import getenv
from coop_manager.base.routes import base


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config['SECRET_KEY'] = getenv('SECRET_KEY')
    app.register_blueprint(base)
    return app


app = create_app()


def main():
    app.run(
        host='0.0.0.0',
        port=5555,
        debug=True
    )


if __name__ == '__main__':
    main()
