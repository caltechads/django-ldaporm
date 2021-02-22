VERSION = 1.0.3
PACKAGE = django-ldaporm

#======================================================================

version:
	@echo $(VERSION)

clean:
	rm -rf dist *.egg-info
	find . -name "*.pyc" -exec rm '{}' ';'

dist: clean
	@python setup.py sdist
	@python setup.py bdist_wheel --universal

pypi: dist
	@twine upload dist/*

tox:
	# create a tox pyenv virtualenv based on 2.7.x
	# install tox and tox-pyenv in that ve
	# actiave that ve before running this
	@tox
