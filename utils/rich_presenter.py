from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.markdown import Markdown
from rich import box
import time


console = Console()


class RichPresenter:
    def __init__(self):
        self.console = Console()

    def banner(self):
        banner_text = """
[bold cyan]
    ███╗   ██╗███████╗██╗   ██╗    ███████╗██╗   ██╗███████╗
    ████╗  ██║██╔════╝╚██╗ ██╔╝    ██╔════╝██║   ██║██╔════╝
    ██╔██╗ ██║█████╗   ╚████╔╝     ███████╗██║   ██║███████╗
    ██║╚██╗██║██╔══╝    ╚██╔╝      ╚════██║██║   ██║╚════██║
    ██║ ╚████║███████╗   ██║       ███████║╚██████╔╝███████║
    ╚═╝  ╚═══╝╚══════╝   ╚═╝       ╚══════╝ ╚═════╝ ╚══════╝
[/bold cyan]
[dim]    Tsundere AI Bot that pretends not to care... but actually does.[/dim]
"""
        self.console.print(Panel(
            Align.center(Markdown(banner_text.strip())),
            box=box.DOUBLE,
            border_style="bright_cyan",
            padding=(1, 2)
        ))

    def startup_header(self):
        self.console.print()
        self.console.rule("[bold bright_cyan]Nova Bot Startup[/bold bright_cyan]", style="bright_cyan")
        self.console.print()

    def service_status(self, services: dict):
        table = Table(
            title="[bold]Service Status[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold bright_cyan",
            border_style="cyan"
        )
        table.add_column("Service", style="cyan", width=20)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Details", style="dim", width=35)

        for name, info in services.items():
            status = info.get("status", "unknown")
            details = info.get("details", "")

            if status == "ok":
                status_text = "[bold green]● READY[/bold green]"
            elif status == "warning":
                status_text = "[bold yellow]● WARN[/bold yellow]"
            elif status == "error":
                status_text = "[bold red]● ERROR[/bold red]"
            else:
                status_text = "[dim]● ?[/dim]"

            table.add_row(name, status_text, details)

        self.console.print(table)

    def config_table(self, config: dict):
        table = Table(
            title="[bold]Configuration[/bold]",
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style="bold magenta",
            border_style="magenta"
        )
        table.add_column("Key", style="magenta", width=25)
        table.add_column("Value", style="white")

        for key, value in config.items():
            table.add_row(key, str(value))

        self.console.print(table)

    def model_info(self, models: dict):
        table = Table(
            title="[bold]AI Models[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold green",
            border_style="green"
        )
        table.add_column("Purpose", style="green", width=20)
        table.add_column("Model", style="white", width=30)
        table.add_column("Provider", style="dim", width=15)

        for purpose, info in models.items():
            model = info.get("model", "N/A")
            provider = info.get("provider", "N/A")
            table.add_row(purpose, model, provider)

        self.console.print(table)

    def trigger_list(self, triggers: list):
        table = Table(
            title="[bold]Supported Triggers[/bold]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold yellow",
            border_style="yellow"
        )
        table.add_column("Type", style="yellow", width=20)
        table.add_column("Example", style="white", width=30)
        table.add_column("Description", style="dim", width=35)

        for trigger in triggers:
            table.add_row(
                trigger.get("type", ""),
                trigger.get("example", ""),
                trigger.get("desc", "")
            )

        self.console.print(table)

    def ready_message(self, bot_name: str, guilds: int, latency: float):
        self.console.print()
        self.console.rule("[bold green]Bot is Ready![/bold green]", style="green")
        self.console.print()

        ready_table = Table(box=box.MINIMAL, show_header=False, padding=(0, 2))
        ready_table.add_column("Key", style="bold cyan")
        ready_table.add_column("Value", style="white")
        ready_table.add_row("Bot", f"[bold]{bot_name}[/bold]")
        ready_table.add_row("Guilds", str(guilds))
        ready_table.add_row("Latency", f"{latency * 1000:.0f}ms")
        ready_table.add_row("Status", "[bold green]Online[/bold green]")

        self.console.print(Panel(
            Align.center(ready_table),
            title="[bold green] Connected [/bold green]",
            border_style="green",
            padding=(1, 2)
        ))

    def error_panel(self, title: str, error: str):
        self.console.print(Panel(
            f"[red]{error}[/red]",
            title=f"[bold red] {title} [/bold red]",
            border_style="red",
            padding=(1, 2)
        ))

    def success_panel(self, title: str, message: str):
        self.console.print(Panel(
            f"[green]{message}[/green]",
            title=f"[bold green] {title} [/bold green]",
            border_style="green",
            padding=(1, 2)
        ))

    def info_panel(self, title: str, message: str):
        self.console.print(Panel(
            f"[cyan]{message}[/cyan]",
            title=f"[bold cyan] {title} [/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))

    def loading_animation(self, message: str, duration: float = 1.0):
        with self.console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots"):
            time.sleep(duration)

    def process_trigger(self, trigger_type: str, user: str, channel: str):
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="bold yellow")
        table.add_column("Value", style="white")
        table.add_row("Trigger", trigger_type)
        table.add_row("User", user)
        table.add_row("Channel", channel)

        self.console.print(Panel(
            table,
            title="[bold yellow] New Message [/bold yellow]",
            border_style="yellow",
            padding=(0, 1)
        ))

    def rag_stats(self, nuggets_found: int, relevant: int):
        self.console.print(
            f"  [dim]RAG:[/dim] [cyan]{nuggets_found}[/cyan] nuggets loaded → "
            f"[green]{relevant}[/green] relevant selected"
        )

    def compaction_stats(self, usage_before: float, usage_after: float):
        self.console.print(
            f"  [dim]Compaction:[/dim] [yellow]{usage_before:.1%}[/yellow] → "
            f"[green]{usage_after:.1%}[/green]"
        )

    def response_stats(self, tokens: int, latency: float):
        self.console.print(
            f"  [dim]Response:[/dim] [magenta]{tokens}[/magenta] tokens in "
            f"[cyan]{latency:.2f}s[/cyan]"
        )

    def footer(self):
        self.console.print()
        self.console.rule("[dim]Nova Bot v1.0 - Tsundere AI[/dim]", style="dim")
        self.console.print()


rich = RichPresenter()
