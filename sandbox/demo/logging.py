import structlog
from crequest.middleware import CrequestMiddleware

logger = structlog.get_logger("sphinx_hosting_demo")


def request_context_logging_processor(_, __, event_dict):
    """
    Adds extra runtime event info to our log messages based on the current request.

      ``username``: the username of the logged in user, if user is logged in.
      ``remote_ip``: the REMOTE_ADDR address. django-xff will handle properly setting
            this if we're behind a proxy
      ``superuser``: True if the current User is a superuser

    Does not overwrite any event info that's already been set in the logging call.
    """
    request = CrequestMiddleware.get_request()
    if request is not None:
        try:
            # django-xff will set this appropriately to the actual client IP when
            # we are behind a proxy
            client_ip = request.META["REMOTE_ADDR"]
        except AttributeError:
            # Sometimes there will be a current request, but it's not a real
            # request (during tests). If we can't get the real client ip, just
            # use a placeholder.
            client_ip = "fake IP"
        event_dict.setdefault("remote_ip", client_ip)
        event_dict.setdefault("username", request.user.username or "AnonymousUser")
        event_dict.setdefault("superuser", request.user.is_superuser)
    return event_dict


def censor_password_processor(_, __, event_dict):
    """
    Automatically censors any logging context key called "password",
    "password1", or "password2".
    """
    for password_key_name in ("password", "password1", "password2"):
        if password_key_name in event_dict:
            event_dict[password_key_name] = "*CENSORED*"
    return event_dict
