from flask import Blueprint, render_template


def create() -> Blueprint:
    return Blueprint(
        'base',
        __name__,
        static_folder='static',
        static_url_path='/base/static',
        template_folder='templates',
    )


base = create()


@base.route('/')
def index():
    return render_template('index.html')
