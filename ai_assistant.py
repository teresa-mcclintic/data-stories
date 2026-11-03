"""Optional AI question planner; all statistics are computed locally with pandas.

Only column metadata and the user's question go to the API. Uploaded rows are NOT sent.
The model cannot run code, select unsupported operations, or generate numerical evidence.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

import pandas as pd
import plotly.express as px

ALLOWED = {'trend','group','distribution','relationship'}
AGG = {'average':'mean','total':'sum','median':'median','count':'count'}
MAX_QUESTION = 400


class UnsupportedQuestion(ValueError):
    """Question cannot safely be answered by the current analysis engine."""


def plan_question(question: str, df: pd.DataFrame, labels: dict[str,str],
                  api_key: str, model: str = 'gpt-4.1-mini') -> dict[str,Any]:
    """Return a validated analysis plan; do not transfer raw data rows."""
    if not 3 <= len(question.strip()) <= MAX_QUESTION:
        raise UnsupportedQuestion('Enter a question between 3 and 400 characters.')
    if not api_key:
        raise UnsupportedQuestion('AI has not been configured.')
    from openai import OpenAI

    schema = [{'name':str(col), 'label':labels.get(col,str(col)),
               'type':'date' if pd.api.types.is_datetime64_any_dtype(df[col])
               else 'numeric' if pd.api.types.is_numeric_dtype(df[col]) else 'category'}
              for col in df.columns][:80]
    instructions = (
        'You are a cautious data-analysis planner. Return ONLY a JSON object. '
        'The dataset contains the exact fields in the user message. '
        'Never invent fields. Choose ONE of trend, group, distribution, relationship, unsupported. '
        'Return JSON keys: type, date, value, category, x, y, aggregation, period, reason. '
        'Use null for unused fields. Allowed aggregation: average,total,median,count. '
        'Allowed period: original,year,decade,month. '
        'Trend requires a date field plus numeric value. Group requires an existing category field plus numeric value. '
        'For time questions about calendar years, decades or months choose trend, '
        'and derive the period from the date field. Do not invent a decade column. '
        'Distribution requires numeric value. Relationship requires two different numeric fields. '
        'If the requested question needs a statistical test, causal inference, predictions, '
        'specific filtering, season-year grouping, or analysis outside these operations, '
        'choose unsupported and explain briefly. Never imply correlation means causation. '
        'Only use total for additive quantities (counts, sales, snowfall, precipitation); '
        'prefer average otherwise. Data rows and computed results have NOT been supplied.'
    )
    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    result = client.responses.create(
        model=model, instructions=instructions,
        input=json.dumps({'columns':schema,'question':question},ensure_ascii=False),
        max_output_tokens=320,
        store=False,
    )
    raw = result.output_text.strip()
    if raw.startswith('```'):
        raw = raw.strip('`').removeprefix('json').strip()
    try:
        plan = json.loads(raw)
    except (json.JSONDecodeError,TypeError) as exc:
        raise UnsupportedQuestion('Could not interpret that question. Please rephrase it.') from exc
    if not isinstance(plan,dict):
        raise UnsupportedQuestion('Could not interpret that question. Please rephrase it.')
    if plan.get('type') not in ALLOWED:
        raise UnsupportedQuestion(str(plan.get('reason') or
            'That question needs a calculation this first AI version does not support.')[:300])

    kinds = {c:'date' if pd.api.types.is_datetime64_any_dtype(df[c])
             else 'numeric' if pd.api.types.is_numeric_dtype(df[c]) else 'category'
             for c in df.columns}
    def require(key,kind):
        field = plan.get(key)
        if not isinstance(field,str) or field not in kinds or kinds[field]!=kind:
            raise UnsupportedQuestion('That question cannot be calculated using the available column types.')
        return field
    # Repair a common planning mistake: decades must be derived from dates,
    # rather than treated as a pre-existing grouping column.
    if re.search(r'\bdecades?\b', question, flags=re.IGNORECASE):
        date_cols = [c for c,t in kinds.items() if t=='date']
        value = plan.get('value')
        if kinds.get(value) != 'numeric':
            value = next((c for c in (plan.get('y'), plan.get('x'))
                          if kinds.get(c)=='numeric'), None)
        if date_cols and value is not None:
            date_col = plan.get('date') if plan.get('date') in date_cols else date_cols[0]
            plan.update(type='trend', date=date_col, value=value, period='decade')
    typ=plan['type']
    if typ=='trend':
        require('date','date'); require('value','numeric')
        if plan.get('period') not in ('original','year','decade','month'):
            plan['period']='original'
    elif typ=='group':
        cat=plan.get('category')
        if not isinstance(cat,str) or cat not in kinds or kinds[cat]=='date':
            raise UnsupportedQuestion('A suitable grouping column was not found.')
        require('value','numeric')
    elif typ=='distribution':
        require('value','numeric')
    else:
        x=require('x','numeric'); y=require('y','numeric')
        if x==y: raise UnsupportedQuestion('Two different numeric columns are required.')
    if plan.get('aggregation') not in AGG:
        plan['aggregation']='average'
    return plan


def calculate(df: pd.DataFrame, plan: dict, labels: dict[str,str]):
    """Return (verified factual explanation, figure) calculated without AI."""
    kind = plan['type']
    def label(c): return labels.get(c,c)
    if kind=='trend':
        date,value=plan['date'],plan['value']
        data=df[[date,value]].dropna().copy()
        if len(data)<3: raise UnsupportedQuestion('There are too few observations for a trend chart.')
        period=plan.get('period','original')
        method=plan['aggregation']
        # For monthly source records annual totals can be misleading when a year is incomplete.
        if period in ('year','decade'):
            years=data[date].dt.year
            if data[date].dt.to_period('M').nunique()>=36 and data[date].dt.month.nunique()>6:
                nmonths=data.assign(_year=years,_month=data[date].dt.month).groupby('_year')['_month'].nunique()
                good_years=nmonths[nmonths==12].index
                data=data[years.isin(good_years)]
                if data.empty:
                    raise UnsupportedQuestion('No complete calendar years are available for this comparison.')
        if period=='year': data['Period']=data[date].dt.year.astype(str)
        elif period=='decade': data['Period']=((data[date].dt.year//10)*10).astype(str)+'s'
        elif period=='month': data['Period']=data[date].dt.month_name()
        else: data['Period']=data[date]
        # For additive monthly values, compare mean ANNUAL totals per decade
        # rather than raw decade totals (which depend on the number of years).
        if period=='decade' and method=='total':
            annual=data.assign(Year=data[date].dt.year).groupby('Year',as_index=False)[value].sum()
            annual['Period']=((annual['Year']//10)*10).astype(str)+'s'
            g=annual.groupby('Period',as_index=False)[value].mean()
        else:
            g=data.groupby('Period',as_index=False,sort=(period!='month'))[value].agg(AGG[method])
        if period=='month':
            months=list(__import__('calendar').month_name)[1:]
            g['Period']=pd.Categorical(g['Period'],categories=months,ordered=True)
            g=g.sort_values('Period')
        if len(g)<2: raise UnsupportedQuestion('Not enough different time periods to compare.')
        title = (f'Average annual total {label(value)} by decade'
                 if period=='decade' and method=='total'
                 else f'{method.title()} {label(value)} by {period if period!="original" else "date"}')
        fig=px.line(g,x='Period',y=value,markers=True,title=title,
                    labels={value:label(value),'Period':period.title() if period!='original' else 'Date'})
        stats=f'{len(g)} periods, minimum {g[value].min():,.2f}, maximum {g[value].max():,.2f}.'
        note=('Only years with all 12 months represented were included. '
              if period in ('year','decade') and data[date].dt.month.nunique()>6 else '')
        return f'{method.title()} {label(value)} across {stats} {note}These are descriptive results, not proof of a long-term trend.',fig
    if kind=='group':
        cat,val=plan['category'],plan['value']
        data=df[[cat,val]].dropna()
        if data[cat].nunique()>35: raise UnsupportedQuestion('Too many groups to show clearly (maximum 35).')
        g=data.groupby(cat,as_index=False,observed=True)[val].agg(AGG[plan['aggregation']])
        if len(g)<2: raise UnsupportedQuestion('There must be at least two groups.')
        g=g.sort_values(val,ascending=False)
        fig=px.bar(g,x=cat,y=val,title=f'{plan["aggregation"].title()} {label(val)} by {label(cat)}',
                   labels={cat:label(cat),val:label(val)})
        winner=g.iloc[0]
        return f'Compared {len(g)} groups. The highest {plan["aggregation"]} of {label(val)} is {winner[val]:,.2f} for {winner[cat]}. Differences are descriptive and do not establish causes.',fig
    if kind=='distribution':
        val=plan['value']; x=df[val].dropna()
        if len(x)<3: raise UnsupportedQuestion('Too few values for a distribution.')
        fig=px.histogram(df,x=val,nbins=25,title=f'Distribution of {label(val)}',labels={val:label(val)})
        return f'Among {len(x):,} values, the median {label(val)} is {x.median():,.2f}, with a range from {x.min():,.2f} to {x.max():,.2f}.',fig
    x,y=plan['x'],plan['y']
    data=df[[x,y]].dropna()
    if len(data)<4: raise UnsupportedQuestion('Too few paired values to compare.')
    corr=data[x].corr(data[y])
    if not math.isfinite(float(corr)): raise UnsupportedQuestion('A correlation could not be calculated.')
    fig=px.scatter(data.head(10000),x=x,y=y,title=f'{label(x)} and {label(y)}',
                   labels={x:label(x),y:label(y)})
    return f'Across {len(data):,} paired records, the Pearson correlation is {corr:+.2f}. This describes a linear association, not causation. The chart displays at most 10,000 records.',fig
