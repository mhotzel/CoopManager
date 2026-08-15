"""Route configuration for the base views"""
from flask import Blueprint, render_template


def create() -> Blueprint:
    """Creates and returns the BluePrint for the base features"""
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
    """Delivers a view for the index page"""
    return render_template('index.html')
