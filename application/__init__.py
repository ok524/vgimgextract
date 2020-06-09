import os

from flask import Flask, render_template, send_from_directory
from flask_cors import CORS, cross_origin

#application factory function
def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        MONGODB_DB='yourapp',
        MONGODB_HOST='mongodb',
        MONGODB_PORT=27017,
        MYSQL_DATABASE_USER='root',
        MYSQL_DATABASE_PASSWORD='yourapp_password',
        MYSQL_DATABASE_DB='yourapp',
        MYSQL_DATABASE_HOST='mysql',
        REDIS_URL = 'redis://redis:6379',
        REDIS_HOST = 'redis',
        REDIS_PORT = 6379,
        REDIS_DB = '0',
        QUEUES = ['default'], # instance/config.py will override
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # initialise db module
    import application.database as database
    database.init_app(app)

    # initialise redis connection
    import application.redis_connection as redis_connection
    redis_connection.init_app(app)
    import application.redis_worker as redis_worker
    redis_worker.init_app(app)

    #register blueprints
    from application.yourapp import yourapp
    app.register_blueprint(yourapp, url_prefix='/yourapp')

    from application.documents import documents
    app.register_blueprint(documents, url_prefix='/documents')

    # handle output_files
    @app.route('/output_files/<path:path>')
    @cross_origin()
    def output_files(path):
        return send_from_directory(
            os.path.join("/home/flask/app/output_files", ""),
            path)

    # handle favicon
    @app.route('/favicon.ico')
    @cross_origin()
    def favicon():
        return send_from_directory(
            os.path.join("/home/flask/app/application", "static"),
            "favicon.ico", mimetype="image/vnd.microsoft.icon")

    # handle the docs yaml
    @app.route('/api.yaml')
    @cross_origin()
    def apiyaml():
        return send_from_directory(
            os.path.join("/home/flask/app/documentation", ""),
            "api.yaml", mimetype="text/yaml")

    # handle the docs page
    @app.route('/docs')
    @cross_origin()
    def docs():
        return render_template('docs.html')

    # handle the list page
    @app.route('/list')
    def listing():
        return render_template('list.html')

    # handle the main page
    @app.route('/')
    def index():
        return render_template('index.html')

    #register error handlers
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(500, server_error)

    return app

def page_not_found(e):
    return "404 error", 404

def server_error(e):
    return "500 error", 500

app = create_app()
