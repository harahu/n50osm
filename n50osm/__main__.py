import click


@click.command()
@click.option("--municipality", help="Municipality id")
@click.option("--category", help="Data category")
def main(municipality: str, category: str) -> None:
    click.echo(f"{municipality} {category}")


if __name__ == "__main__":
    main()
