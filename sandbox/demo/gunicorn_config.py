import environ

env = environ.Env()

##### General #####
bind = "unix:/tmp/app.sock"
workers = 8
worker_class = "sync"
daemon = False
timeout = 300
worker_tmp_dir = "/tmp"  # noqa: S108
# requires futures module for threads > 1
threads = 1

##### Devel #####
reload = True

##### Logging #####
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {
        "handlers": ["syslog_console"],
        "level": "INFO",
    },
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["syslog_console"],
            "propagate": False,
            "qualname": "gunicorn.error",
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["access_console"],
            "propagate": False,
            "qualname": "gunicorn.access",
        },
    },
    "handlers": {
        "syslog_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "syslog",
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "access_log",
        },
    },
    "formatters": {
        "syslog": {
            "()": "logging.Formatter",
            "fmt": "SYSLOG %(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
        "access_log": {
            "()": "logging.Formatter",
            "fmt": "GUNICORN_ACCESS %(asctime)s %(message)s",
        },
    },
}
