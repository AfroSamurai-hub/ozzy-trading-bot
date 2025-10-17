"""
Centralized currency formatting for the trading system

Philosophy: "Evolve, not add and break"
- All calculations stay in USD internally
- Only display/formatting changes to support ZAR
- Single source of truth for exchange rates
- Easy to extend with more currencies
"""
import os
from typing import Union

class CurrencyFormatter:
    """Format amounts in user's preferred currency"""
    
    def __init__(self):
        # Read from environment or default to USD
        self.currency = os.getenv("OZZY_CURRENCY", "USD").upper()
        self.usd_to_zar = float(os.getenv("OZZY_USD_TO_ZAR", "18.50"))
        
        self.symbols = {
            "USD": "$",
            "ZAR": "R"
        }
        
        self.names = {
            "USD": "US Dollar",
            "ZAR": "South African Rand"
        }
    
    def format(self, usd_amount: Union[float, int], decimals: int = 2) -> str:
        """
        Format amount in configured currency
        
        Args:
            usd_amount: Amount in USD (base currency for all internal calculations)
            decimals: Decimal places (default: 2)
        
        Returns:
            Formatted string like "$1,234.56" or "R22,839.36"
        
        Examples:
            >>> formatter = CurrencyFormatter()
            >>> formatter.currency = "USD"
            >>> formatter.format(1000)
            '$1,000.00'
            >>> formatter.currency = "ZAR"
            >>> formatter.usd_to_zar = 18.5
            >>> formatter.format(1000)
            'R18,500.00'
        """
        if self.currency == "ZAR":
            amount = usd_amount * self.usd_to_zar
            symbol = "R"
        else:
            amount = usd_amount
            symbol = "$"
        
        return f"{symbol}{amount:,.{decimals}f}"
    
    def format_signed(self, usd_amount: Union[float, int], decimals: int = 2) -> str:
        """
        Format amount with explicit +/- sign (for P&L display)
        
        Args:
            usd_amount: Amount in USD
            decimals: Decimal places
        
        Returns:
            Formatted string like "+$123.45" or "-R2,283.83"
        """
        if self.currency == "ZAR":
            amount = usd_amount * self.usd_to_zar
            symbol = "R"
        else:
            amount = usd_amount
            symbol = "$"
        
        return f"{symbol}{amount:+,.{decimals}f}"
    
    def get_exchange_rate(self) -> float:
        """Get current USD to display currency exchange rate"""
        if self.currency == "ZAR":
            return self.usd_to_zar
        return 1.0

# Global instance (singleton pattern)
_formatter = CurrencyFormatter()

def format_currency(usd_amount: Union[float, int], decimals: int = 2) -> str:
    """
    Format amount in user's configured currency
    
    Args:
        usd_amount: Amount in USD
        decimals: Decimal places
    
    Returns:
        Formatted currency string
    
    Examples:
        >>> format_currency(5000)
        '$5,000.00'  # if OZZY_CURRENCY=USD
        'R92,500.00'  # if OZZY_CURRENCY=ZAR and rate=18.5
    """
    return _formatter.format(usd_amount, decimals)

def format_currency_signed(usd_amount: Union[float, int], decimals: int = 2) -> str:
    """
    Format amount with +/- sign for P&L display
    
    Args:
        usd_amount: Amount in USD
        decimals: Decimal places
    
    Returns:
        Formatted currency string with sign
    """
    return _formatter.format_signed(usd_amount, decimals)

def get_currency_code() -> str:
    """Get current currency code (USD, ZAR, etc.)"""
    return _formatter.currency

def get_currency_symbol() -> str:
    """Get current currency symbol ($, R, etc.)"""
    return _formatter.symbols.get(_formatter.currency, "$")

def get_currency_name() -> str:
    """Get current currency full name"""
    return _formatter.names.get(_formatter.currency, "US Dollar")

def get_exchange_rate() -> float:
    """Get current USD to display currency exchange rate"""
    return _formatter.get_exchange_rate()
