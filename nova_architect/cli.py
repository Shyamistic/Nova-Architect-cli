import click
import os
import sys
import time
import subprocess
import webbrowser
import json
import socket
from pathlib import Path
from datetime import datetime
import threading

# Rich imports with graceful fallback
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    RICH = True
except ImportError:
    RICH = False

console = Console() if RICH else None

CONFIG_DIR = Path.home() / ".nova-architect"
CONFIG_FILE = CONFIG_DIR / "config.json"
ENV_FILE = CONFIG_DIR / ".env"

BANNER = """
╭─────────────────────────────────────────╮
│                                         │
│   ⚡ Nova Architect  v2.0.0             │
│   Build AWS infrastructure from         │
│   plain English                         │
│                                         │
╰─────────────────────────────────────────╯
"""

def print_banner():
    if RICH:
        console.print(Panel(Text("⚡ Nova Architect  v2.0.0\nBuild AWS infrastructure from\nplain English", justify="center", style="bold orange1"), expand=False))
    else:
        print(BANNER)

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    
    # Also write a .env file for uvicorn/backend
    with open(ENV_FILE, "w") as f:
        for k, v in config.items():
            if k != "setup_complete" and k != "setup_at":
                f.write(f"{k.upper()}={v}\n")

def get_free_port(start_port=8000, max_attempts=20):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except socket.error:
                continue
    return None

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Nova Architect CLI — Build AWS from English."""
    if ctx.invoked_subcommand is None:
        config = load_config()
        if not config.get("setup_complete"):
            ctx.invoke(setup)
        else:
            ctx.invoke(start)

@main.command()
def setup():
    """Interactive setup wizard for AWS and Nova Act."""
    print_banner()
    if RICH:
        console.print("\n[bold]Welcome! Let's get you set up in about 2 minutes.[/bold]\n")
    else:
        print("\nWelcome! Let's get you set up in about 2 minutes.\n")

    config = load_config()

    # Step 1: AWS Credentials
    if RICH:
        console.print("[bold cyan]Step 1 of 3 — AWS Credentials[/bold cyan]")
        console.print("[dim]These stay on your machine. Never sent anywhere.[/dim]\n")
    else:
        print("Step 1 of 3 — AWS Credentials")
        print("These stay on your machine. Never sent anywhere.\n")

    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    if aws_access_key:
        msg = f"Found AWS credentials ending in ...{aws_access_key[-4:]}. Use these?"
        if Confirm.ask(msg) if RICH else input(f"{msg} [Y/n]: ").lower() != 'n':
            config["aws_access_key_id"] = aws_access_key.strip()
            config["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
        else:
            config["aws_access_key_id"] = (Prompt.ask("AWS Access Key ID") if RICH else input("AWS Access Key ID: ")).strip()
            config["aws_secret_access_key"] = (Prompt.ask("AWS Secret Access Key", password=True) if RICH else input("AWS Secret Access Key: ")).strip()
    else:
        config["aws_access_key_id"] = (Prompt.ask("AWS Access Key ID") if RICH else input("AWS Access Key ID: ")).strip()
        config["aws_secret_access_key"] = (Prompt.ask("AWS Secret Access Key", password=True) if RICH else input("AWS Secret Access Key: ")).strip()

    config["aws_region"] = (Prompt.ask("AWS Region", default="us-east-1") if RICH else input("AWS Region [us-east-1]: ") or "us-east-1").strip()

    if RICH: console.print("→ Validating AWS credentials...")
    try:
        import boto3
        client = boto3.client(
            "bedrock", 
            region_name=config["aws_region"],
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"]
        )
        client.list_foundation_models(byProvider="Amazon")
        if RICH: console.print("[bold green]✓ AWS credentials valid — Bedrock accessible[/bold green]\n")
    except Exception as e:
        if RICH: console.print(f"[bold yellow]⚠ Could not validate — check credentials if builds fail[/bold yellow]\n")
        # Log the error for debugging but don't show the secret
        # print(f"Validation error: {e}")

    # Step 2: Nova Act API Key (Optional in IAM mode)
    if RICH:
        console.print("[bold cyan]Step 2 of 3 — Nova Act API Key (Optional)[/bold cyan]")
        console.print("[dim]If using IAM credentials (default), you can leave this blank.[/dim]")
        console.print("[dim]Otherwise, get a key at: [link=https://nova.amazon.com/act]nova.amazon.com/act[/link][/dim]\n")
    else:
        print("Step 2 of 3 — Nova Act API Key (Optional)")
        print("If using IAM credentials (default), you can leave this blank.")
        print("Otherwise, get a key at: https://nova.amazon.com/act\n")

    nova_act_key = os.environ.get("NOVA_ACT_API_KEY")
    if nova_act_key:
        msg = "Found NOVA_ACT_API_KEY in environment. Use it?"
        if Confirm.ask(msg) if RICH else input(f"{msg} [Y/n]: ").lower() != 'n':
            config["nova_act_api_key"] = nova_act_key.strip()
        else:
            typed_key = (Prompt.ask("Nova Act API Key", password=True, default="") if RICH else input("Nova Act API Key (optional): ")).strip()
            if typed_key:
                config["nova_act_api_key"] = typed_key
    else:
        typed_key = (Prompt.ask("Nova Act API Key", password=True, default="") if RICH else input("Nova Act API Key (optional): ")).strip()
        if typed_key:
            config["nova_act_api_key"] = typed_key

    # Step 3: Browser Setup
    if RICH:
        console.print("[bold cyan]Step 3 of 3 — Browser Setup[/bold cyan]")
        console.print("[dim]Nova Act needs Chromium to automate the AWS Console[/dim]\n")
    else:
        print("Step 3 of 3 — Browser Setup")
        print("Nova Act needs Chromium to automate the AWS Console\n")

    if Confirm.ask("Install Chromium now? (~170MB)") if RICH else input("Install Chromium now? (~170MB) [Y/n]: ").lower() != 'n':
        if RICH: console.print("→ Installing Chromium browser for Nova Act automation...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
        if RICH: console.print("[bold green]✓ Chromium installed[/bold green]\n")

    config["setup_complete"] = True
    config["setup_at"] = datetime.now().isoformat()
    save_config(config)

    if RICH:
        console.print(Panel(Text("✓ Setup complete!\n\nRun: nova-architect start\nConfig: " + str(CONFIG_DIR), style="bold green"), expand=False))
    else:
        print("\n✓ Setup complete!\nRun: nova-architect start\nConfig: " + str(CONFIG_DIR))

@main.command()
@click.option("--port", default=0, help="Custom port to run on.")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically.")
@click.option("--headless", is_flag=True, help="Run Nova Act without visible browser.")
@click.option("--demo", is_flag=True, help="Run in demo mode (no real AWS actions).")
def start(port, no_browser, headless, demo):
    """Start the Nova Architect dashboard."""
    config = load_config()
    if not config.get("setup_complete"):
        if RICH: console.print("[bold red]Error: Setup not complete. Run: nova-architect setup[/bold red]")
        sys.exit(1)

    print_banner()

    actual_port = port if port > 0 else get_free_port()
    url = f"http://localhost:{actual_port}"

    if RICH:
        table = Table(show_header=False, box=None)
        table.add_row("Dashboard", f"[link={url}]{url}[/link]")
        table.add_row("Region", config.get("aws_region", "us-east-1"))
        table.add_row("Nova Act", "headless" if headless else "visible browser")
        table.add_row("Mode", "demo" if demo else "live")
        console.print(table)
        console.print(f"\n→ Starting server on port {actual_port}...")
    else:
        print(f"Dashboard    {url}")
        print(f"Region       {config.get('aws_region', 'us-east-1')}")
        print(f"Nova Act     {'headless' if headless else 'visible browser'}")
        print(f"Mode         {'demo' if demo else 'live'}")
        print(f"\n→ Starting server on port {actual_port}...")

    # Set env vars for the backend
    os.environ["AWS_ACCESS_KEY_ID"] = config.get("aws_access_key_id", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = config.get("aws_secret_access_key", "")
    os.environ["AWS_REGION"] = config.get("aws_region", "us-east-1")
    os.environ["NOVA_ACT_API_KEY"] = config.get("nova_act_api_key", "")
    os.environ["NOVA_ACT_HEADLESS"] = "true" if headless else "false"
    os.environ["DEMO_MODE"] = "true" if demo else "false"
    os.environ["PORT"] = str(actual_port)
    os.environ["DATABASE_URL"] = str(CONFIG_DIR / "nova-architect.db")

    # Find the backend directory
    import nova_architect
    pkg_dir = Path(nova_architect.__file__).parent
    backend_dir = pkg_dir / "backend"
    
    # Fallback for dev mode
    if not backend_dir.exists():
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if not backend_dir.exists():
            backend_dir = Path(__file__).resolve().parent / "backend"

    if not no_browser:
        def _open():
            time.sleep(2.0)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()
        if RICH: console.print(f"→ Opening {url} in your browser...")

    if RICH: console.print(f"→ Starting server on port {actual_port}...")
    
    # Change to backend dir so relative imports in main.py work
    os.chdir(backend_dir)
    # Also add to path for uvicorn string import resolution
    sys.path.insert(0, str(backend_dir))
    
    import uvicorn
    try:
        # log_level="info" helps debug startup issues
        uvicorn.run("main:app", host="0.0.0.0", port=actual_port, reload=False, log_level="info")
    except KeyboardInterrupt:
        if RICH: console.print("\n[bold orange1]Nova Architect stopped.[/bold orange1]")
        else: print("\nNova Architect stopped.")

@main.command()
def doctor():
    """Diagnose setup and dependency issues."""
    print_banner()
    if RICH: console.print("\nChecking your Nova Architect setup...\n")
    
    config = load_config()
    results = []

    # Python Version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    results.append(("Python version", py_ver, sys.version_info >= (3, 11)))

    # AWS Credentials
    aws_ok = False
    aws_val = "not set"
    if config.get("aws_access_key_id"):
        try:
            import boto3
            client = boto3.client(
                "bedrock", 
                region_name=config.get("aws_region", "us-east-1"),
                aws_access_key_id=config["aws_access_key_id"],
                aws_secret_access_key=config["aws_secret_access_key"]
            )
            client.list_foundation_models(byProvider="Amazon")
            aws_ok = True
            aws_val = f"...{config['aws_access_key_id'][-4:]}"
        except Exception:
            aws_val = "invalid"
    results.append(("AWS credentials", aws_val, aws_ok))

    # Nova Act SDK
    sdk_ok = False
    try:
        import nova_act
        sdk_ok = True
    except ImportError: pass
    results.append(("Nova Act SDK", "installed" if sdk_ok else "missing", sdk_ok))

    # Nova Act API Key
    has_key = len(config.get("nova_act_api_key", "")) > 10
    results.append(("Nova Act API key", "configured" if has_key else "optional (IAM mode)", True))

    # Playwright
    pw_ok = False
    try:
        subprocess.run(["playwright", "--version"], capture_output=True, check=True)
        pw_ok = True
    except Exception: pass
    results.append(("Playwright", "installed" if pw_ok else "missing", pw_ok))

    # Chromium
    chrome_ok = False
    if pw_ok:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                p.chromium.launch(headless=True).close()
                chrome_ok = True
        except Exception: pass
    results.append(("Chromium", "installed" if chrome_ok else "missing", chrome_ok))

    # Config File
    results.append(("Config file", "~/.nova-architect" if CONFIG_FILE.exists() else "missing", CONFIG_FILE.exists()))

    # AWS Region
    results.append(("AWS Region", config.get("aws_region", "missing"), bool(config.get("aws_region"))))

    if RICH:
        table = Table(title="Health Check Summary")
        table.add_column("Check", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Status", justify="center")
        for name, val, ok in results:
            table.add_row(name, val, "[green]✓ OK[/green]" if ok else "[red]✗ FAIL[/red]")
        console.print(table)
        if all(r[2] for r in results):
            console.print("\n[bold green]✓ All checks passed. Run: nova-architect start[/bold green]")
        else:
            console.print("\n[bold red]Some checks failed. Run: nova-architect setup[/bold red]")
    else:
        print("Check              Value              Status")
        print("─────────────────────────────────────────────")
        for name, val, ok in results:
            print(f"{name:<18} {val:<18} {'✓ OK' if ok else '✗ FAIL'}")

@main.command()
def reset():
    """Delete all nova-architect-* resources from AWS."""
    if RICH:
        console.print("[bold red]⚠ This will delete all nova-architect-* AWS resources from your account.[/bold red]")
    else:
        print("⚠ This will delete all nova-architect-* AWS resources from your account.")
    
    if not (Confirm.ask("Are you sure?") if RICH else input("Are you sure? [y/N]: ").lower() == 'y'):
        return

    config = load_config()
    import boto3
    session = boto3.Session(
        aws_access_key_id=config.get("aws_access_key_id"),
        aws_secret_access_key=config.get("aws_secret_access_key"),
        region_name=config.get("aws_region", "us-east-1")
    )
    
    found = False
    # S3
    s3 = session.resource("s3")
    for bucket in s3.buckets.all():
        if bucket.name.startswith("nova-architect-"):
            found = True
            if RICH: console.print(f"→ Deleting S3: {bucket.name}...")
            bucket.objects.all().delete()
            bucket.delete()
            if RICH: console.print(f"[green]✓ Deleted S3: {bucket.name}[/green]")

    # DynamoDB
    ddb = session.client("dynamodb")
    tables = ddb.list_tables()["TableNames"]
    for table in tables:
        if table.startswith("nova-architect-"):
            found = True
            if RICH: console.print(f"→ Deleting DynamoDB: {table}...")
            ddb.delete_table(TableName=table)
            if RICH: console.print(f"[green]✓ Deleted DynamoDB: {table}[/green]")

    # Lambda
    lam = session.client("lambda")
    fns = lam.list_functions()["Functions"]
    for fn in fns:
        if fn["FunctionName"].startswith("nova-architect-"):
            found = True
            if RICH: console.print(f"→ Deleting Lambda: {fn['FunctionName']}...")
            lam.delete_function(FunctionName=fn["FunctionName"])
            if RICH: console.print(f"[green]✓ Deleted Lambda: {fn['FunctionName']}[/green]")

    # API Gateway
    apg = session.client("apigateway")
    apis = apg.get_rest_apis()["items"]
    for api in apis:
        if api["name"] == "nova-architect-api" or api["name"].startswith("nova-architect-"):
            found = True
            if RICH: console.print(f"→ Deleting API Gateway: {api['name']}...")
            apg.delete_rest_api(restApiId=api["id"])
            if RICH: console.print(f"[green]✓ Deleted API Gateway: {api['name']}[/green]")
    
    if not found:
        if RICH: console.print("[dim]No nova-architect resources found.[/dim]")
        else: print("No nova-architect resources found.")

@main.command()
def version():
    """Show version information."""
    print("Nova Architect v2.0.0")

@main.command()
def upgrade():
    """Upgrade Nova Architect to the latest version."""
    if RICH: console.print("→ Upgrading Nova Architect via pip...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "nova-architect"])

if __name__ == "__main__":
    main()
