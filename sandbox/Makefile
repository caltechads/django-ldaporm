VERSION = 1.2.0

PACKAGE = django_ldaporm_demo

.PHONY: clean dist build force-build tag dev dev-detached devup devdown logall log exec restart docker-clean docker-destroy-db docker-destroy list  package
#======================================================================

clean:
	rm -rf *.tar.gz dist *.egg-info *.rpm
	find . -name "*.pyc" -exec rm '{}' ';'
	find . -name "__pycache__" -exec rm -rf '{}' ';'

dist: clean
	@uv build --sdist

uv.lock:
	@uv lock

compile: uv.lock
	@uv pip compile pyproject.toml -o requirements.txt

package:
	(cd ..; uv build --sdist)
	cp ../dist/django_ldaporm-${VERSION}.tar.gz django-ldaporm.tar.gz

build: compile
	docker build -t ${PACKAGE}:${VERSION} .
	docker tag ${PACKAGE}:${VERSION} ${PACKAGE}:latest
	docker image prune -f

force-build: compile
	docker build --no-cache -t ${PACKAGE}:${VERSION} .
	docker tag ${PACKAGE}:${VERSION} ${PACKAGE}:latest
	docker image prune -f

dev:
	docker compose up

dev-detached:
	docker compose up -d

devup: dev-detached

devdown:
	docker compose down

logall:
	docker compose logs -f

log:
	docker logs -f django_ldaporm_demo

exec:
	docker exec -it django_ldaporm_demo /bin/bash

restart:
	docker compose restart django_ldaporm_demo

scout:
	docker scout cves --only-severity=critical,high ${PACKAGE}:${VERSION}

docker-clean:
	docker stop $(shell docker ps -a -q)
	docker rm $(shell docker ps -a -q)

docker-destroy-db: docker-clean
	docker volume rm sandbox_ldaporm_demo_data
	docker volume rm sandbox_ldaporm_demo_ldap_data

docker-destroy: docker-clean docker-destroy-db

list:
	@$(MAKE) -pRrq -f $(lastword $(MAKEFILE_LIST)) : 2>/dev/null | awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}' | sort | egrep -v -e '^[^[:alnum:]]' -e '^$@$$' | xargs
