"""Transparent, rule-based insights for CSV datasets. No model/API calls."""
from __future__ import annotations
from io import BytesIO
import re
import numpy as np
import pandas as pd

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 80


def load_csv(raw: bytes) -> pd.DataFrame:
    if len(raw) > MAX_BYTES:
        raise ValueError('File exceeds the 8 MB limit.')
    errors = []
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            df = pd.read_csv(BytesIO(raw), encoding=enc, sep=None, engine='python', on_bad_lines='error')
            break
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            errors.append(str(exc))
    else:
        raise ValueError('Could not read this CSV. Check its encoding and separators.')
    if df.empty:
        raise ValueError('This CSV has no data rows.')
    if df.shape[1] > MAX_COLUMNS or len(df) > MAX_ROWS:
        raise ValueError(f'Please use up to {MAX_ROWS:,} rows and {MAX_COLUMNS} columns for this version.')
    df.columns = [str(c).strip() or f'Column {i + 1}' for i,c in enumerate(df.columns)]
    if len(set(df.columns)) != len(df.columns):
        raise ValueError('Column names must be unique after trimming spaces.')
    for col in df.select_dtypes(include=['object','string']).columns:
        series = df[col].dropna().astype(str).str.strip()
        if series.empty:
            continue
        if (series.str.fullmatch(r'\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?').mean() >= 0.9):
            converted = pd.to_datetime(df[col], errors='coerce')
            if converted.notna().sum() >= 0.9 * df[col].notna().sum():
                df[col] = converted
    if 'year' in df.columns and 'month' in df.columns:
        year = pd.to_numeric(df['year'], errors='coerce')
        month = pd.to_numeric(df['month'], errors='coerce')
        if year.between(1800, 2200).mean() > .95 and month.between(1,12).mean() > .95:
            # Don't replace either original column. A real date is helpful for a monthly time series.
            new_name = 'Date (from year + month)'
            if new_name not in df:
                df[new_name] = pd.to_datetime({'year': year, 'month': month, 'day': 1}, errors='coerce')
    return df


def profile(df: pd.DataFrame) -> dict:
    numeric = [c for c in df.select_dtypes(include='number').columns if not df[c].dropna().empty]
    dates = df.select_dtypes(include='datetime').columns.tolist()
    categories = [c for c in df.columns if c not in numeric + dates and 1 < df[c].nunique(dropna=True) <= 35]
    missing = int(df.isna().sum().sum())
    return {'numeric': numeric, 'dates': dates, 'categories': categories,
            'rows': len(df), 'cols': len(df.columns), 'missing': missing,
            'duplicate_rows': int(df.duplicated().sum())}


def fmt(x: float) -> str:
    return f'{x:,.2f}'.rstrip('0').rstrip('.') if abs(x) < 1e9 else f'{x:,.3g}'


def discover(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Return findings with a chart recipe. Numbers are calculated from the source rows."""
    p = profile(df)
    findings = []
    def add(kind, title, summary, evidence, recipe, question):
        findings.append(dict(kind=kind, title=title, summary=summary,
                             evidence=evidence, recipe=recipe, question=question))

    # Trend and fluctuation: time series, grouped by actual period and using mean.
    # A mean avoids assuming that each row represents an additive quantity.
    if p['dates'] and p['numeric']:
        d = p['dates'][0]
        for num in p['numeric'][:3]:
            if num.lower() in ('year','month','day','days_recorded','days_in_month'):
                continue
            frame = df[[d,num]].dropna().sort_values(d)
            if len(frame) < 5:
                continue
            times = frame.groupby(d, as_index=False)[num].mean().sort_values(d)
            if len(times) < 5:
                continue
            start, end = float(times[num].iloc[0]), float(times[num].iloc[-1])
            delta = end-start
            direction = 'higher' if delta>0 else 'lower' if delta<0 else 'the same'
            add('time', f'How has {num} changed?',
                f'The first and last observed period averages were {fmt(start)} and {fmt(end)} ({direction} by {fmt(abs(delta))}). This is an endpoint comparison, not proof of a long-term trend.',
                f'{len(times):,} distinct time points; grouped by period using the mean.',
                {'type':'time', 'date':d,'value':num},
                'Do the values change steadily or fluctuate? Would a different date range change your conclusion?')
            break

    # Difference between categories, with meaningful category size minimum.
    for cat in p['categories'][:3]:
        for num in p['numeric'][:4]:
            if num.lower() in ('year','month','day'):
                continue
            groups = df.groupby(cat, observed=True)[num].agg(['mean','count']).dropna()
            groups = groups[groups['count'] >= 2]
            if len(groups) < 2:
                continue
            top = groups['mean'].idxmax()
            bottom = groups['mean'].idxmin()
            diff = float(groups.loc[top,'mean'] - groups.loc[bottom,'mean'])
            add('groups',f'Which {cat} groups differ in {num}?',
                f'The highest average is {top} ({fmt(groups.loc[top,"mean"])}); the lowest is {bottom} ({fmt(groups.loc[bottom,"mean"])}). Difference: {fmt(diff)}.',
                'Comparisons use group means and exclude groups with fewer than two values.',
                {'type':'groups','category':cat,'value':num},
                'Are group sizes similar? Would totals tell a different story?')
            break
        if len(findings)>=limit: return findings[:limit]

    # Distribution / outliers using IQR. Honest about what outlier means.
    for num in p['numeric'][:6]:
        if num.lower() in ('year','month','day','days_recorded','days_in_month'):
            continue
        vals = df[num].dropna()
        if len(vals) < 5: continue
        q1, q3 = vals.quantile([.25, .75]); iqr = q3-q1
        if iqr > 0:
            outliers = int(((vals < q1-1.5*iqr) | (vals > q3+1.5*iqr)).sum())
        else:
            outliers = 0
        add('distribution', f'What is typical for {num}?',
            f'Median: {fmt(vals.median())}; middle 50%: {fmt(q1)} to {fmt(q3)}. {outliers:,} values fall outside the standard 1.5×IQR outlier fences.',
            f'{len(vals):,} nonmissing observations; outlier labels are a flag for exploration, not errors.',
            {'type':'distribution','value':num},
            'Is the distribution symmetrical? Are unusual observations meaningful?')
        if len(findings)>=limit: return findings[:limit]

    # Relationship, only describe strength (not cause).
    candidates = [c for c in p['numeric'] if c.lower() not in ('year','month','day','days_recorded','days_in_month')]
    best = None
    for i,a in enumerate(candidates[:8]):
        for b in candidates[i+1:8]:
            pairs = df[[a,b]].dropna()
            if len(pairs)<8 or pairs[a].nunique()<3 or pairs[b].nunique()<3:continue
            r = pairs[a].corr(pairs[b])
            if pd.notna(r) and (best is None or abs(r)>abs(best[0])):
                best=(r,a,b,len(pairs))
    if best and abs(best[0])>=.3:
        r,a,b,n=best
        add('relationship',f'Are {a} and {b} related?',
            f'Pearson correlation is {r:+.2f}, suggesting a {"positive" if r>0 else "negative"} linear association. Correlation does not establish causation.',
            f'Calculated from {n:,} paired nonmissing observations.',
            {'type':'relationship','x':a,'y':b},
            'Could other factors explain the relationship? Do unusual points influence it?')
    if p['missing'] and len(findings)<limit:
        total=df.shape[0]*df.shape[1]
        add('quality','Are any values missing?',
            f'{p["missing"]:,} of {total:,} cells ({p["missing"]/total:.1%}) are blank. Missing values may affect conclusions.',
            'Counted across all columns and rows.', {'type':'quality'},
            'Are the missing values concentrated in one column or time period?')
    return findings[:limit]


def plot_finding(df: pd.DataFrame, finding: dict):
    import plotly.express as px
    r = finding['recipe']; kind = r['type']
    if kind == 'time':
        d,v=r['date'],r['value']
        grouped=df[[d,v]].dropna().groupby(d,as_index=False)[v].mean().sort_values(d)
        fig=px.line(grouped,x=d,y=v,markers=True, title='Average by time period')
    elif kind == 'groups':
        c,v=r['category'],r['value']
        grouped=df.groupby(c,as_index=False, observed=True)[v].mean().sort_values(v,ascending=False)
        fig=px.bar(grouped,x=c,y=v, title='Average by group')
    elif kind == 'distribution':
        fig=px.histogram(df,x=r['value'],nbins=30, title='Distribution of values')
    elif kind == 'relationship':
        fig=px.scatter(df.head(5000),x=r['x'],y=r['y'], title='Relationship between variables')
    else:
        counts=df.isna().sum().reset_index()
        counts.columns=['Column','Missing values']
        fig=px.bar(counts,x='Column',y='Missing values',title='Missing data by column')
    fig.update_layout(template='plotly_white',font_family='Arial',margin=dict(l=20,r=20,t=50,b=25))
    return fig


def json_ready(value):
    """Keep saved report entries primitive and JSON serializable."""
    import json
    return json.loads(json.dumps(value,default=str))
