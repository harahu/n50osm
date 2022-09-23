from invoke import task


@task
def lint(c):
    c.run("poetry run flake8")
    c.run("poetry run black --check .")


@task
def format(c):
    c.run("poetry run isort .")
    c.run("poetry run black --preview .")


@task
def package(c):
    c.run(
        'poetry install && mkdir -p dist && poetry run zipapp -p "/usr/bin/env python3"'
        " dist/n50"
    )
