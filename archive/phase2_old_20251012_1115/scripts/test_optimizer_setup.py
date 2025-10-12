#!/usr/bin/env python3
"""
Quick test script for the optimizer suite
Tests with a small sample to verify everything works
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

console = Console()

def test_database():
    """Check if database exists and has trades"""
    import sqlite3
    
    console.print("\n[cyan]🔍 Checking database...[/cyan]")
    
    try:
        conn = sqlite3.connect('ozzy_simple.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM trades WHERE exit_timestamp IS NOT NULL")
        count = cursor.fetchone()[0]
        
        console.print(f"[green]✅ Found {count} completed trades in database[/green]")
        
        if count < 50:
            console.print("[yellow]⚠️  Warning: Less than 50 trades. Optimization may not be reliable.[/yellow]")
            console.print("[yellow]   Recommendation: Generate 200+ trades before optimizing[/yellow]")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Database error: {e}[/red]")
        return False


def test_dependencies():
    """Check if all required dependencies are installed"""
    console.print("\n[cyan]🔍 Checking dependencies...[/cyan]")
    
    missing = []
    
    try:
        import pandas
        console.print("[green]✅ pandas installed[/green]")
    except ImportError:
        missing.append("pandas")
        console.print("[red]❌ pandas missing[/red]")
    
    try:
        import numpy
        console.print("[green]✅ numpy installed[/green]")
    except ImportError:
        missing.append("numpy")
        console.print("[red]❌ numpy missing[/red]")
    
    try:
        import rich
        console.print("[green]✅ rich installed[/green]")
    except ImportError:
        missing.append("rich")
        console.print("[red]❌ rich missing[/red]")
    
    if missing:
        console.print(f"\n[red]Missing dependencies: {', '.join(missing)}[/red]")
        console.print("[yellow]Install with: pip install pandas numpy rich[/yellow]")
        return False
    
    return True


def test_api_access():
    """Check if we can access Bybit API"""
    console.print("\n[cyan]🔍 Checking API access...[/cyan]")
    
    try:
        from bybit_client import BybitClient
        
        client = BybitClient()
        candles = client.get_candles("BTCUSDT", "1", 10)
        
        if candles:
            console.print(f"[green]✅ API accessible - fetched {len(candles)} candles[/green]")
            return True
        else:
            console.print("[yellow]⚠️  API returned no data[/yellow]")
            return False
            
    except Exception as e:
        console.print(f"[yellow]⚠️  API test failed: {e}[/yellow]")
        console.print("[dim]This is OK if rate limited. Optimizer will retry.[/dim]")
        return True  # Continue anyway


def main():
    console.print("╔═══════════════════════════════════════════════════════════╗")
    console.print("║  [bold cyan]OPTIMIZER SUITE - SYSTEM CHECK[/bold cyan]                            ║")
    console.print("╚═══════════════════════════════════════════════════════════╝")
    
    # Run tests
    deps_ok = test_dependencies()
    db_ok = test_database()
    api_ok = test_api_access()
    
    console.print("\n" + "═" * 60)
    console.print("[bold]SUMMARY[/bold]")
    console.print("═" * 60)
    
    if deps_ok and db_ok:
        console.print("\n[bold green]✅ System is ready for optimization![/bold green]\n")
        console.print("[bold]Quick Start:[/bold]")
        console.print("  [cyan]python scripts/combined_optimizer.py[/cyan]")
        console.print()
        console.print("[bold]Or test individual optimizers:[/bold]")
        console.print("  [dim]python scripts/rsi_optimizer.py --top 5[/dim]")
        console.print("  [dim]python scripts/ema_optimizer.py --top 5[/dim]")
        console.print()
    else:
        console.print("\n[bold yellow]⚠️  Please fix issues above before running optimization[/bold yellow]\n")
        
        if not deps_ok:
            console.print("[yellow]1. Install dependencies:[/yellow]")
            console.print("   [cyan]pip install pandas numpy rich[/cyan]")
            console.print()
        
        if not db_ok:
            console.print("[yellow]2. Generate more trading data:[/yellow]")
            console.print("   [cyan]./super_turbo.py[/cyan]")
            console.print("   [dim](Generates 70-100 trades in 5-10 minutes)[/dim]")
            console.print()


if __name__ == "__main__":
    main()
