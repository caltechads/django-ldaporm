#!/bin/bash

if test $(git rev-parse --abbrev-ref HEAD) = "master"; then
    if test -z "$(git status --untracked-files=no --porcelain)"; then
        MSG="$(git log -1 --pretty=%B)"
        echo "$MSG" | grep "Bump version"
        if test $? -eq 0; then
            VERSION=$(echo "$MSG" | awk -F→ '{print $2}')
            echo "---------------------------------------------------"
            echo "Releasing version ${VERSION} ..."
            echo "---------------------------------------------------"
            echo 
            echo 
            git checkout build
            git merge master
            git push --tags origin master build
            git checkout master
        else
            echo "Last commit was not a bumpversion; aborting."
            echo "Last commit message: ${MSG}"
        fi
    else
        git status
        echo
        echo
        echo "------------------------------------------------------"
        echo "You have uncommitted changes; aborting."
        echo "------------------------------------------------------"
    fi
else
    echo "You're not on master; aborting."
fi
