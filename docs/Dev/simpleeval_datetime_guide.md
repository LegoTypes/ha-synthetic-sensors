# DateTime and Duration Functions for simpleeval

## Overview

This document provides a comprehensive guide for extending simpleeval with datetime and duration functionality. Since
simpleeval only includes basic functions by default (`rand()`, `randint()`, `int()`, `float()`, `str()`), datetime
capabilities must be added through custom functions and configurations.

## Table of Contents

1. [Basic Setup](#basic-setup)
2. [Core DateTime Functions](#core-datetime-functions)
3. [Duration and Arithmetic Functions](#duration-and-arithmetic-functions)
4. [Advanced Date Operations](#advanced-date-operations)
5. [Formatting and Parsing](#formatting-and-parsing)
6. [Business Logic Functions](#business-logic-functions)
7. [Security Considerations](#security-considerations)
8. [Complete Implementation Examples](#complete-implementation-examples)
9. [Testing and Validation](#testing-and-validation)

## Basic Setup

### Required Imports

```python
from simpleeval import SimpleEval, DEFAULT_FUNCTIONS
from datetime import datetime, date, time, timedelta
import calendar
import time as time_module
```

### Minimal DateTime Extension

```python
def create_datetime_evaluator():
    """Create a SimpleEval instance with basic datetime support"""

    functions = DEFAULT_FUNCTIONS.copy()
    functions.update({
        # Core datetime constructors
        'datetime': datetime,
        'date': date,
        'time': time,
        'timedelta': timedelta,

        # Current time functions
        'now': datetime.now,
        'today': date.today,
        'utcnow': datetime.utcnow,
    })

    # Allow access to common datetime attributes
    allowed_attrs = {
        datetime: {'year', 'month', 'day', 'hour', 'minute', 'second', 'microsecond', 'weekday'},
        date: {'year', 'month', 'day', 'weekday'},
        time: {'hour', 'minute', 'second', 'microsecond'},
        timedelta: {'days', 'seconds', 'microseconds', 'total_seconds'},
    }

    return SimpleEval(functions=functions, allowed_attrs=allowed_attrs)
```

## Core DateTime Functions

### Basic Constructor Functions

```python
def safe_datetime(*args, **kwargs):
    """Safe datetime constructor with validation"""
    try:
        return datetime(*args, **kwargs)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid datetime parameters: {e}")

def safe_date(*args, **kwargs):
    """Safe date constructor with validation"""
    try:
        return date(*args, **kwargs)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date parameters: {e}")

def safe_timedelta(*args, **kwargs):
    """Safe timedelta constructor with validation"""
    try:
        return timedelta(*args, **kwargs)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid timedelta parameters: {e}")
```

### Current Time Functions

```python
def current_timestamp():
    """Get current Unix timestamp"""
    return time_module.time()

def current_year():
    """Get current year"""
    return datetime.now().year

def current_month():
    """Get current month"""
    return datetime.now().month

def current_day():
    """Get current day of month"""
    return datetime.now().day
```

## Duration and Arithmetic Functions

### Duration Calculation Functions

```python
def days_between(start_date, end_date):
    """Calculate days between two dates"""
    if not isinstance(start_date, (date, datetime)) or not isinstance(end_date, (date, datetime)):
        raise TypeError("Both arguments must be date or datetime objects")
    return (end_date - start_date).days

def hours_between(start_time, end_time):
    """Calculate hours between two datetime objects"""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_time - start_time).total_seconds() / 3600

def minutes_between(start_time, end_time):
    """Calculate minutes between two datetime objects"""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_time - start_time).total_seconds() / 60

def seconds_between(start_time, end_time):
    """Calculate seconds between two datetime objects"""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_time - start_time).total_seconds()
```

### Duration Creation Helpers

```python
def days(n):
    """Create timedelta for n days"""
    return timedelta(days=n)

def hours(n):
    """Create timedelta for n hours"""
    return timedelta(hours=n)

def minutes(n):
    """Create timedelta for n minutes"""
    return timedelta(minutes=n)

def seconds(n):
    """Create timedelta for n seconds"""
    return timedelta(seconds=n)

def weeks(n):
    """Create timedelta for n weeks"""
    return timedelta(weeks=n)
```

### Metadata Integration Functions

These functions are specifically designed for integration with entity metadata access:

```python
def minutes_between(start_datetime, end_datetime):
    """Calculate minutes between two datetime objects.

    Designed for metadata formulas like:
    minutes_between(metadata(state, 'last_changed'), now())
    """
    if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_datetime - start_datetime).total_seconds() / 60

def hours_between(start_datetime, end_datetime):
    """Calculate hours between two datetime objects.

    Designed for metadata formulas like:
    hours_between(metadata(state, 'last_updated'), now())
    """
    if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_datetime - start_datetime).total_seconds() / 3600

def seconds_between(start_datetime, end_datetime):
    """Calculate seconds between two datetime objects.

    Designed for metadata formulas like:
    seconds_between(metadata(state, 'last_changed'), now())
    """
    if not isinstance(start_datetime, datetime) or not isinstance(end_datetime, datetime):
        raise TypeError("Both arguments must be datetime objects")
    return (end_datetime - start_datetime).total_seconds()
```

## Advanced Date Operations

### Business Date Functions

```python
def add_business_days(start_date, business_days):
    """Add business days (Mon-Fri) to a date"""
    if not isinstance(start_date, (date, datetime)):
        raise TypeError("start_date must be a date or datetime object")

    current = start_date
    remaining_days = abs(int(business_days))
    direction = 1 if business_days >= 0 else -1

    while remaining_days > 0:
        current += timedelta(days=direction)
        # Monday=0, Sunday=6, so weekdays are 0-4
        if current.weekday() < 5:
            remaining_days -= 1

    return current

def is_business_day(check_date):
    """Check if date falls on a business day (Mon-Fri)"""
    if not isinstance(check_date, (date, datetime)):
        raise TypeError("check_date must be a date or datetime object")
    return check_date.weekday() < 5

def next_business_day(from_date):
    """Get the next business day from given date"""
    next_day = from_date + timedelta(days=1)
    while not is_business_day(next_day):
        next_day += timedelta(days=1)
    return next_day

def previous_business_day(from_date):
    """Get the previous business day from given date"""
    prev_day = from_date - timedelta(days=1)
    while not is_business_day(prev_day):
        prev_day -= timedelta(days=1)
    return prev_day
```

### Month and Year Operations

```python
def days_in_month(year, month):
    """Get number of days in a specific month"""
    return calendar.monthrange(year, month)[1]

def first_day_of_month(year, month):
    """Get first day of month"""
    return date(year, month, 1)

def last_day_of_month(year, month):
    """Get last day of month"""
    return date(year, month, days_in_month(year, month))

def add_months(start_date, months):
    """Add months to a date (handles month/year rollover)"""
    if not isinstance(start_date, (date, datetime)):
        raise TypeError("start_date must be a date or datetime object")

    year = start_date.year
    month = start_date.month + months
    day = start_date.day

    # Handle year rollover
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12

    # Handle day overflow (e.g., Jan 31 + 1 month = Feb 28/29)
    max_day = days_in_month(year, month)
    if day > max_day:
        day = max_day

    if isinstance(start_date, datetime):
        return datetime(year, month, day, start_date.hour,
                       start_date.minute, start_date.second, start_date.microsecond)
    else:
        return date(year, month, day)
```

### Holiday and Weekend Functions

```python
def is_weekend(check_date):
    """Check if date falls on weekend (Sat/Sun)"""
    if not isinstance(check_date, (date, datetime)):
        raise TypeError("check_date must be a date or datetime object")
    return check_date.weekday() >= 5

def next_weekday(from_date):
    """Get next weekday (Mon-Fri) from given date"""
    next_day = from_date + timedelta(days=1)
    while is_weekend(next_day):
        next_day += timedelta(days=1)
    return next_day

def days_until_weekend(from_date):
    """Calculate days until next weekend"""
    if not isinstance(from_date, (date, datetime)):
        raise TypeError("from_date must be a date or datetime object")

    days_ahead = 5 - from_date.weekday()  # Saturday is day 5
    if days_ahead <= 0:  # Already weekend
        days_ahead += 7
    return days_ahead
```

## Formatting and Parsing

### Date Formatting Functions

```python
def format_date(dt, format_string='%Y-%m-%d'):
    """Format datetime/date as string"""
    if not isinstance(dt, (date, datetime)):
        raise TypeError("dt must be a date or datetime object")
    return dt.strftime(format_string)

def format_iso(dt):
    """Format datetime in ISO format"""
    if not isinstance(dt, datetime):
        raise TypeError("dt must be a datetime object")
    return dt.isoformat()

def format_friendly(dt):
    """Format datetime in human-friendly format"""
    if not isinstance(dt, (date, datetime)):
        raise TypeError("dt must be a date or datetime object")
    return dt.strftime('%B %d, %Y' if isinstance(dt, date) else '%B %d, %Y at %I:%M %p')
```

### Date Parsing Functions

```python
def parse_date(date_string, format_string='%Y-%m-%d'):
    """Parse string to date object"""
    try:
        return datetime.strptime(date_string, format_string).date()
    except ValueError as e:
        raise ValueError(f"Cannot parse '{date_string}' with format '{format_string}': {e}")

def parse_datetime(datetime_string, format_string='%Y-%m-%d %H:%M:%S'):
    """Parse string to datetime object"""
    try:
        return datetime.strptime(datetime_string, format_string)
    except ValueError as e:
        raise ValueError(f"Cannot parse '{datetime_string}' with format '{format_string}': {e}")

def parse_iso(iso_string):
    """Parse ISO format string to datetime"""
    try:
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f"Cannot parse ISO string '{iso_string}': {e}")
```

## Business Logic Functions

### Age and Duration Calculations

```python
def age_in_years(birth_date, reference_date=None):
    """Calculate age in years from birth date"""
    if reference_date is None:
        reference_date = date.today()

    if not isinstance(birth_date, (date, datetime)):
        raise TypeError("birth_date must be a date or datetime object")
    if not isinstance(reference_date, (date, datetime)):
        raise TypeError("reference_date must be a date or datetime object")

    age = reference_date.year - birth_date.year

    # Adjust if birthday hasn't occurred this year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age

def duration_in_words(start_time, end_time):
    """Convert duration to human-readable format"""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise TypeError("Both arguments must be datetime objects")

    delta = end_time - start_time

    if delta.days > 0:
        return f"{delta.days} days, {delta.seconds // 3600} hours"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600} hours, {(delta.seconds % 3600) // 60} minutes"
    elif delta.seconds > 60:
        return f"{delta.seconds // 60} minutes, {delta.seconds % 60} seconds"
    else:
        return f"{delta.seconds} seconds"
```

### Deadline and Schedule Functions

```python
def is_overdue(deadline, reference_time=None):
    """Check if deadline has passed"""
    if reference_time is None:
        reference_time = datetime.now()

    if not isinstance(deadline, datetime):
        raise TypeError("deadline must be a datetime object")
    if not isinstance(reference_time, datetime):
        raise TypeError("reference_time must be a datetime object")

    return reference_time > deadline

def time_until_deadline(deadline, reference_time=None):
    """Calculate time remaining until deadline"""
    if reference_time is None:
        reference_time = datetime.now()

    if not isinstance(deadline, datetime):
        raise TypeError("deadline must be a datetime object")
    if not isinstance(reference_time, datetime):
        raise TypeError("reference_time must be a datetime object")

    return deadline - reference_time

def deadline_in_days(deadline, reference_time=None):
    """Calculate days until deadline"""
    delta = time_until_deadline(deadline, reference_time)
    return delta.days + (1 if delta.seconds > 0 else 0)
```

## Security Considerations

### Safe Function Wrappers

When implementing datetime functions for simpleeval, consider these security aspects:

1. **Input Validation**: Always validate inputs to prevent errors
2. **Resource Limits**: Avoid functions that could consume excessive resources
3. **Attribute Access**: Carefully control which datetime attributes are accessible
4. **Current Time Access**: Consider whether expressions should access current time

```python
def create_secure_datetime_evaluator(allow_current_time=True, max_year=2100):
    """Create a secure datetime evaluator with safety limits"""

    def safe_datetime_constructor(year, month=1, day=1, hour=0, minute=0, second=0, microsecond=0):
        # Validate reasonable year range
        if not (1900 <= year <= max_year):
            raise ValueError(f"Year must be between 1900 and {max_year}")
        return datetime(year, month, day, hour, minute, second, microsecond)

    def safe_timedelta_constructor(days=0, seconds=0, microseconds=0,
                                 milliseconds=0, minutes=0, hours=0, weeks=0):
        # Limit maximum duration to prevent abuse
        total_days = days + (weeks * 7)
        if abs(total_days) > 36500:  # ~100 years
            raise ValueError("Timedelta too large (max 100 years)")
        return timedelta(days=days, seconds=seconds, microseconds=microseconds,
                        milliseconds=milliseconds, minutes=minutes,
                        hours=hours, weeks=weeks)

    functions = DEFAULT_FUNCTIONS.copy()
    functions.update({
        'datetime': safe_datetime_constructor,
        'date': date,
        'timedelta': safe_timedelta_constructor,
        # Add current time functions only if allowed
        **(({'now': datetime.now, 'today': date.today} if allow_current_time else {})),
        # Add all other custom functions here...
    })

    # Restricted attribute access
    allowed_attrs = {
        datetime: {'year', 'month', 'day', 'hour', 'minute', 'second', 'weekday'},
        date: {'year', 'month', 'day', 'weekday'},
        timedelta: {'days', 'seconds', 'total_seconds'},
    }

    return SimpleEval(functions=functions, allowed_attrs=allowed_attrs)
```

## HA Synthetic Sensors Integration Example

### Enhanced SimpleEval for HA Synthetic Sensors

```python
def create_ha_synthetic_evaluator():
    """Create enhanced SimpleEval optimized for HA synthetic sensor metadata integration."""

    functions = DEFAULT_FUNCTIONS.copy()
    functions.update({
        # Core datetime constructors
        'datetime': datetime,
        'date': date,
        'timedelta': timedelta,

        # Current time functions (essential for metadata calculations)
        'now': datetime.now,
        'today': date.today,

        # Duration creation (replaces custom Duration objects)
        'days': lambda n: timedelta(days=n),
        'hours': lambda n: timedelta(hours=n),
        'minutes': lambda n: timedelta(minutes=n),
        'seconds': lambda n: timedelta(seconds=n),
        'weeks': lambda n: timedelta(weeks=n),

        # Metadata integration functions (NEW - essential for metadata access)
        'minutes_between': minutes_between,
        'hours_between': hours_between,
        'seconds_between': seconds_between,
        'days_between': days_between,

        # Business logic functions
        'add_business_days': add_business_days,
        'is_business_day': is_business_day,
        'is_weekend': is_weekend,

        # Formatting functions
        'format_date': format_date,
        'format_friendly': format_friendly,
        'format_iso': format_iso,
    })

    # Critical: Allow access to timedelta methods for SimpleEval compatibility
    allowed_attrs = {
        datetime: {'year', 'month', 'day', 'hour', 'minute', 'second', 'weekday'},
        date: {'year', 'month', 'day', 'weekday'},
        timedelta: {'days', 'seconds', 'total_seconds'},  # Essential for .total_seconds()
    }

    return SimpleEval(functions=functions, allowed_attrs=allowed_attrs)

# Example usage with metadata integration
evaluator = create_ha_synthetic_evaluator()

# Metadata handler provides datetime objects, enhanced SimpleEval calculates
context = {
    'last_changed': datetime(2024, 1, 1, 10, 0),  # From metadata(state, 'last_changed')
    'now': datetime.now(),
    'grace_period': 15
}

# These work perfectly in enhanced SimpleEval:
result1 = evaluator.eval('minutes_between(last_changed, now)', context)  # Returns float
result2 = evaluator.eval('minutes_between(last_changed, now) < grace_period', context)  # Returns bool
result3 = evaluator.eval('format_friendly(last_changed)', context)  # Returns string
```

### Real YAML Integration Examples

```yaml
# Example from metadata access proposal - this works with enhanced SimpleEval
sensors:
  power_with_grace:
    entity_id: sensor.span_panel_instantaneous_power
    formula: "state if is_fresh else 'stale'"
    variables:
      is_fresh:
        formula: "minutes_since_update < grace_period"
      minutes_since_update:
        formula: "minutes_between(metadata(state, 'last_updated'), now())"
      grace_period: 15
    attributes:
      last_update_time:
        formula: "format_friendly(metadata(state, 'last_updated'))"
      status:
        formula: "'fresh' if is_fresh else 'stale'"
```

## Complete Implementation Examples

### Example 1: Project Management Evaluator

```python
def create_project_evaluator():
    """DateTime evaluator optimized for project management calculations"""

    functions = DEFAULT_FUNCTIONS.copy()
    functions.update({
        # Core datetime
        'datetime': datetime,
        'date': date,
        'timedelta': timedelta,
        'now': datetime.now,
        'today': date.today,

        # Duration calculations
        'days_between': days_between,
        'hours_between': hours_between,
        'add_business_days': add_business_days,
        'is_business_day': is_business_day,

        # Project-specific functions
        'is_overdue': is_overdue,
        'deadline_in_days': deadline_in_days,
        'duration_in_words': duration_in_words,

        # Helper functions
        'days': days,
        'hours': hours,
        'weeks': weeks,
    })

    allowed_attrs = {
        datetime: {'year', 'month', 'day', 'hour', 'minute', 'weekday'},
        date: {'year', 'month', 'day', 'weekday'},
        timedelta: {'days', 'seconds', 'total_seconds'},
    }

    return SimpleEval(functions=functions, allowed_attrs=allowed_attrs)

# Usage example
evaluator = create_project_evaluator()
evaluator.names.update({
    'project_start': date(2024, 1, 15),
    'project_deadline': datetime(2024, 6, 30, 17, 0),
    'task_duration': timedelta(days=14)
})

# Example expressions
print(evaluator.eval('days_between(project_start, today())'))  # Days since start
print(evaluator.eval('is_overdue(project_deadline)'))          # Is project overdue?
print(evaluator.eval('add_business_days(today(), 10)'))        # 10 business days from now
```

### Example 2: Financial/Business Evaluator

```python
def create_business_evaluator():
    """DateTime evaluator for business and financial calculations"""

    functions = DEFAULT_FUNCTIONS.copy()
    functions.update({
        # Core datetime
        'datetime': datetime,
        'date': date,
        'timedelta': timedelta,
        'today': date.today,

        # Business date functions
        'add_business_days': add_business_days,
        'is_business_day': is_business_day,
        'next_business_day': next_business_day,
        'is_weekend': is_weekend,

        # Month/year functions
        'add_months': add_months,
        'first_day_of_month': first_day_of_month,
        'last_day_of_month': last_day_of_month,
        'days_in_month': days_in_month,

        # Age calculations
        'age_in_years': age_in_years,

        # Formatting
        'format_date': format_date,
        'format_friendly': format_friendly,
    })

    allowed_attrs = {
        datetime: {'year', 'month', 'day', 'weekday'},
        date: {'year', 'month', 'day', 'weekday'},
        timedelta: {'days', 'total_seconds'},
    }

    return SimpleEval(functions=functions, allowed_attrs=allowed_attrs)
```

## Testing and Validation

### Unit Test Examples

```python
import unittest
from datetime import datetime, date, timedelta

class TestDateTimeFunctions(unittest.TestCase):

    def setUp(self):
        self.evaluator = create_datetime_evaluator()

    def test_basic_datetime_creation(self):
        result = self.evaluator.eval('datetime(2024, 1, 1)')
        self.assertEqual(result, datetime(2024, 1, 1))

    def test_date_arithmetic(self):
        self.evaluator.names['start'] = date(2024, 1, 1)
        result = self.evaluator.eval('start + timedelta(days=30)')
        self.assertEqual(result, date(2024, 1, 31))

    def test_duration_calculation(self):
        self.evaluator.names.update({
            'start': datetime(2024, 1, 1, 10, 0),
            'end': datetime(2024, 1, 1, 14, 30)
        })
        result = self.evaluator.eval('hours_between(start, end)')
        self.assertEqual(result, 4.5)

    def test_business_days(self):
        # Test with a known Monday
        monday = date(2024, 1, 1)  # Assuming this is a Monday
        self.evaluator.names['monday'] = monday
        result = self.evaluator.eval('add_business_days(monday, 5)')
        # Should be the following Monday (5 business days later)
        expected = monday + timedelta(days=7)  # Next Monday
        self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()
```

### Validation and Error Handling

```python
def validate_datetime_expression(expression, evaluator):
    """Validate a datetime expression before evaluation"""
    try:
        # Check for potentially dangerous operations
        dangerous_patterns = ['__', 'import', 'exec', 'eval', 'open']
        if any(pattern in expression for pattern in dangerous_patterns):
            raise ValueError(f"Expression contains potentially dangerous operations")

        # Evaluate the expression
        result = evaluator.eval(expression)

        # Validate result type
        allowed_types = (datetime, date, timedelta, int, float, str, bool)
        if not isinstance(result, allowed_types):
            raise TypeError(f"Expression returned unexpected type: {type(result)}")

        return result

    except Exception as e:
        raise ValueError(f"Invalid datetime expression '{expression}': {e}")
```

## Conclusion

This implementation provides a comprehensive datetime and duration extension for simpleeval that covers:

- **Basic datetime operations** (creation, current time access)
- **Duration calculations** (between dates, business days, etc.)
- **Advanced date arithmetic** (month/year operations, business logic)
- **Formatting and parsing** (string conversion, ISO formats)
- **Security considerations** (input validation, resource limits)
- **Real-world applications** (project management, business calculations)

The modular design allows you to pick and choose which functions to include based on your specific needs, while maintaining
simpleeval's security benefits through controlled function and attribute access.

### Recommendations

1. **Start Small**: Begin with basic functions and add more as needed
2. **Validate Inputs**: Always validate datetime inputs to prevent errors
3. **Consider Security**: Be cautious about allowing current time access in user expressions
4. **Test Thoroughly**: Include comprehensive tests for edge cases
5. **Document Usage**: Provide clear examples for end users

### Essential Functions for HA Synthetic Sensors

For HA synthetic sensor metadata integration, these functions are **required**:

**Core Functions**:

- `now()`, `today()` - Current time access
- `minutes_between()`, `hours_between()`, `days_between()` - Metadata calculations
- `format_friendly()`, `format_date()` - Human-readable output

**Duration Functions**:

- `minutes()`, `hours()`, `days()` - Create timedelta objects (replacing custom Duration)
- Must return Python `timedelta` objects for SimpleEval `allowed_attrs` compatibility

**Key Implementation Points**:

- All datetime functions must work with Python `datetime`/`timedelta` objects
- No method calls like `.total_seconds()` in formulas - use calculation functions instead
- MetadataHandler returns raw `datetime` objects for function consumption
- Enhanced SimpleEval handles all calculations, comparisons, and formatting

This approach provides powerful datetime capabilities while maintaining the safety and simplicity that makes simpleeval
attractive for expression evaluation.
