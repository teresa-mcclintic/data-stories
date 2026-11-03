"""Human-readable presentation metadata. Never changes underlying data columns."""
from __future__ import annotations
import re
import pandas as pd

ACRONYMS = {'id':'ID','usd':'USD','gpa':'GPA','api':'API','url':'URL','csv':'CSV'}
UNITS = {'inches':'inches','inch':'inches','mm':'mm','cm':'cm','kg':'kg',
         'lbs':'lb','lb':'lb','minutes':'minutes','hours':'hours','percent':'%',
         'percentage':'%','pct':'%','usd':'USD','dollars':'USD'}

def infer_label(name: str) -> str:
    raw = str(name).strip()
    if raw.lower() == 'date (from year + month)':
        return 'Date'
    parts = [p for p in re.split(r'[_\s\-]+', raw) if p]
    if not parts:
        return raw
    if parts[-1].lower() in UNITS and len(parts)>1:
        unit = UNITS[parts[-1].lower()]
        base = ' '.join(ACRONYMS.get(p.lower(),p.capitalize()) for p in parts[:-1])
        return f'{base} ({unit})'
    if raw.lower() == 'ski_season_jul_jun':
        return 'Ski season (July–June)'
    if raw.lower() == 'days_recorded':
        return 'Days with records'
    if raw.lower() == 'days_in_month':
        return 'Days in month'
    return ' '.join(ACRONYMS.get(p.lower(), p.capitalize()) for p in parts)

def infer_grain(columns) -> str:
    c = {str(x).lower() for x in columns}
    if {'year','month'}.issubset(c): return 'month'
    if 'date' in c or 'day' in c: return 'observation'
    if 'year' in c: return 'year'
    return 'observation'

def replace_fields(text: str, labels: dict[str,str]) -> str:
    """Replace complete field-name tokens, not substrings of ordinary words."""
    result = str(text)
    for field in sorted(labels, key=len, reverse=True):
        display = labels[field]
        if display and field != display:
            result = re.sub(r'(?<![\w])'+re.escape(str(field))+r'(?![\w])',
                            lambda _m: display, result, flags=re.IGNORECASE)
    return result

def style_figure(fig, labels: dict[str,str]):
    """Presentation-only edits; preserve traces and numerical calculations."""
    for axis in ('xaxis','yaxis'):
        obj = getattr(fig.layout, axis, None)
        if obj is not None and obj.title and obj.title.text:
            obj.title.text = replace_fields(obj.title.text,labels)
    if fig.layout.title and fig.layout.title.text:
        fig.layout.title.text = replace_fields(fig.layout.title.text,labels)
    if fig.layout.legend and fig.layout.legend.title and fig.layout.legend.title.text:
        fig.layout.legend.title.text = replace_fields(fig.layout.legend.title.text,labels)
    for tr in fig.data:
        if getattr(tr,'name',None):
            tr.name = replace_fields(str(tr.name), labels)
        if getattr(tr,'hovertemplate',None):
            tr.hovertemplate = replace_fields(tr.hovertemplate, labels)
    return fig

def column_role(df: pd.DataFrame, col: str) -> str:
    s=df[col]
    if pd.api.types.is_datetime64_any_dtype(s): return 'Date / time'
    if col.lower() in ('year','month','day'): return 'Time component'
    if pd.api.types.is_numeric_dtype(s):
        if col.lower().endswith('_id') or col.lower()=='id': return 'Identifier (review)'
        return 'Number'
    return 'Category or text'
