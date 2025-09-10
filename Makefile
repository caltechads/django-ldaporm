VERSION = 1.3.0
PACKAGE = django-ldaporm

#======================================================================

version:
	@echo $(VERSION)

clean:
	rm -rf dist *.egg-info
	find . -name "*.pyc" -exec rm '{}' ';'
	find . -name "__pycache__" | xargs rm -rf

dist: clean
	@python -m build

release: dist
	@bin/release.sh

compile: uv.lock
	@uv pip compile --group demo --group docs --group test pyproject.toml -o requirements.txt

tox:
	# create a tox pyenv virtualenv based on 2.7.x
	# install tox and tox-pyenv in that ve
	# actiave that ve before running this
	@tox
