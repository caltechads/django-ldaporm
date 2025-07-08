FROM python:3.13-slim AS build

# This part builds the virtual environment and installs the system dependencies
# needed to do so.

ENV UV_PROJECT_ENVIRONMENT=/ve \
    UV_COMPILE_BYTECODE=1      \
    UV_LINK_MODE=copy          \
    UV_PYTHON_DOWNLOADS=never

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update --allow-insecure-repositories && \
    apt-get upgrade -y && \
    apt-get install --yes --no-install-recommends \
        gcc g++ rustc cargo \
        # Some of our python dependencies come from github or gitlab
        git \
        # Mysql dependencies for mysqlclient
        mariadb-client libmariadb-dev pkg-config \
        # LDAP libraries for python-ldap
        libldap-dev libsasl2-dev libldap-common \
        # Various dependencies for common requirements.
        libcurl4-openssl-dev libreadline-dev libssl-dev locales-all libffi-dev libxslt1-dev \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /bin/bash /bin/sh && \
    /usr/local/bin/pip install --upgrade supervisor uv pip setuptools wheel

COPY ./django-ldaporm.tar.gz /django-ldaporm.tar.gz

RUN --mount=type=cache,target=/uv-cache \
    --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv --cache-dir=/uv-cache sync --frozen --no-install-project


FROM python:3.13-slim

ENV HISTCONTROL=ignorespace:ignoredups  \
    IPYTHONDIR=/etc/ipython             \
    # Add the venv's binaries, and the /app folder, to the PATH.
    PATH=/ve/bin:/app:$PATH             \
    PYCURL_SSL_LIBRARY=nss              \
    SHELL_PLUS=ipython                  \
    # Setting this env var is all you need to do to set the timezone in Debian.
    TZ=America/Los_Angeles              \
    # Tell uv where the venv is, and to always copy instead of hardlink, which is needed for a mounted uv cache.
    UV_PROJECT_ENVIRONMENT=/ve          \
    UV_LINK_MODE=copy                   \
    # Tell python which venv to use.
    VIRTUAL_ENV=/ve



# We set this env var for this command only, so that installers know we're not running them interactively.
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update --allow-insecure-repositories && \
    apt-get upgrade -y && \
    apt-get install --yes --no-install-recommends \
        nginx \
        git \
        # We need these mariadb packages for python to connect to mysql. mysqlclient also depends on pkg-config.
        mariadb-client libmariadb-dev pkg-config \
        # LDAP libraries for python-ldap
        libldap-dev libsasl2-dev libldap-common \
        # App specific dependencies
        sqlite3 \
        # Various dependencies for common requirements.
        locales-all \
        # Essential unix utilities that don't come with the base Docker image we use.
        hostname less make procps psmisc tar telnet vim wget which \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /bin/bash /bin/sh && \
    /usr/local/bin/pip install --upgrade uv supervisor setuptools pip && \
    # Add the user under which supervisord, gunicorn, and nginx will run.
    adduser --disabled-password app && \
    # Create the directories that nginx needs to run.
    mkdir -p /var/tmp/nginx/client_body \
        /var/tmp/nginx/proxy \
        /var/tmp/nginx/fastcgi \
        /var/tmp/nginx/uwsgi \
        /var/tmp/nginx/scgi \
    && \
    chown -R app:app /var/tmp/nginx && \
    # Generate a self-signed SSL cert for nginx to use.
    mkdir -p /certs && \
    openssl req -x509 -nodes \
      -subj "/C=US/ST=CA/O=Caltech/CN=localhost.localdomain" \
      -days 3650 \
      -newkey rsa:2048 \
      -keyout /certs/localhost.key \
      -out /certs/localhost.crt && \
    chown -R app:app /certs/* && \
    apt-get autoremove -yqq &&  \
    apt-get autoclean -yqq

COPY --from=build --chown=app:app /ve /ve
ENV PATH=/ve/bin:/usr/local/bin:$PATH

COPY . /app
WORKDIR /app

RUN --mount=type=cache,target=/uv-cache \
    uv --cache-dir=/uv-cache sync --frozen --no-install-project && \
    cp etc/nginx.conf /etc/nginx/nginx.conf && \
    chown app:app /etc/nginx/nginx.conf && \
    cp etc/supervisord.conf /etc/supervisord.conf && \
    chown app:app /etc/supervisord.conf && \
    ./manage.py compilescss --settings=demo.settings_docker -v0 --skip-checks && \
    ./manage.py collectstatic --settings=demo.settings_docker --noinput -v0 -i node_modules && \
    mkdir -p /static && \
    chown -R app:app /app && \
    chown -R app:app /static

EXPOSE 8443

USER app

ENTRYPOINT ["/bin/bash", "/app/bin/entrypoint.sh"]
CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisord.conf"]