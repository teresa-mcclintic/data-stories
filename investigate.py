"""Version 4: question-first, evidence-based follow-up analysis.

Each eligible question belongs to one of three lenses:
- Dig deeper: test a finding more closely
- Change perspective: change the unit or frame of comparison
- Make connections: compare months, periods, or measures

Availability is based on the actual dataset, not hard-coded sample names.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

LANES = ('Dig deeper', 'Change perspective', 'Make connections')


def _style(fig):
    fig.update_layout(template='plotly_white', font_family='Arial',
                      margin=dict(l=20, r=20, t=50, b=25), hovermode='closest')
    return fig


def _date_frame(df, recipe):
    date, value = recipe['date'], recipe['value']
    out = df[[date, value]].dropna().copy()
    out[date] = pd.to_datetime(out[date], errors='coerce')
    return out.dropna().sort_values(date)


def _coverage_years(data, date):
    return data[date].dt.year.nunique() if not data.empty else 0


def _monthly_enough(data, date):
    if data.empty:
        return False
    years = data[date].dt.year.nunique()
    months = data[date].dt.month.nunique()
    return years >= 6 and months >= 6 and len(data) >= 36


def suggest_followups(df: pd.DataFrame, finding: dict) -> list[dict]:
    """Return meaningful, supported follow-up options, each with a question and lens."""
    r = finding['recipe']; kind = r['type']; options = []
    def add(lane, ident, title):
        options.append({'lane': lane, 'id': ident, 'question': title})

    if kind == 'time':
        data = _date_frame(df, r)
        if len(data) < 3: return []
        value = r['value']; years = _coverage_years(data, r['date'])
        add('Dig deeper', 'smoothing', f'How much does {value} fluctuate around its longer-term pattern?')
        if years >= 12:
            add('Change perspective', 'decades', f'How has {value} changed from decade to decade?')
            add('Change perspective', 'earlier_later', 'Do earlier and more recent years tell a different story?')
        elif years >= 3:
            add('Change perspective', 'earlier_later', 'How do the earlier and more recent years compare?')
        if _monthly_enough(data, r['date']):
            add('Make connections', 'months', f'Which months account for differences in {value} between earlier and recent years?')
            add('Make connections', 'early_late', f'Do higher values early in the year tend to accompany higher annual {value}?')
        elif years >= 5:
            add('Make connections', 'year_variation', f'Are extreme {value} years concentrated in a particular period?')

    elif kind == 'groups':
        cat, val = r['category'], r['value']
        data = df[[cat,val]].dropna()
        if len(data) >= 4 and data[cat].nunique() >= 2:
            add('Dig deeper', 'group_spread', f'How much does {val} vary within each {cat} group?')
            add('Change perspective', 'group_method', f'Do the {cat} rankings change when we compare averages, medians, or totals?')
            add('Make connections', 'group_size', f'Could different group sizes affect the comparison of {val}?')

    elif kind == 'distribution':
        val = r['value']
        if df[val].notna().sum() >= 5:
            add('Dig deeper', 'outliers', f'Which {val} values are unusually high or low?')
            add('Change perspective', 'quantiles', f'What does a typical range of {val} look like?')
            dates = df.select_dtypes(include='datetime').columns.tolist()
            if dates and df[dates[0]].dt.year.nunique() >= 3:
                add('Make connections', 'dist_time', f'Has the distribution of {val} shifted between earlier and recent years?')
            else:
                candidates=[c for c in df.select_dtypes(include='number').columns if c!=val and df[c].nunique(dropna=True)>=4]
                if candidates:
                    add('Make connections', 'dist_relation', f'Does {val} vary with another measurement?')

    elif kind == 'relationship':
        x,y=r['x'],r['y']
        if len(df[[x,y]].dropna())>=8:
            add('Dig deeper', 'trim', f'Does the association between {x} and {y} depend on extreme observations?')
            add('Change perspective', 'relationship_groups', 'Do different groups show different patterns?')
            add('Make connections', 'relationship_rank', f'Is the relationship still present when comparing rankings instead of raw values?')

    elif kind == 'quality':
        add('Dig deeper', 'missing', 'Which columns have the most missing values?')
        dates=df.select_dtypes(include='datetime').columns.tolist()
        if dates:
            add('Change perspective', 'missing_time', 'Is missing data more common in some years?')
    return options


def _yearly(data, date, value, method):
    by_year=data.assign(Year=data[date].dt.year).groupby('Year',as_index=False)[value].agg(method)
    return by_year.sort_values('Year')


def _aggregation_ui(key, default='Average'):
    choices=['Average', 'Total', 'Median']
    selected=st.selectbox('How should multiple records in the same period be combined?', choices,
                         index=choices.index(default), key=f'{key}_aggregation',
                         help='Use Total for additive quantities such as snowfall or sales; use Average for temperatures, rates, or percentages.')
    return {'Average':'mean','Total':'sum','Median':'median'}[selected], selected


def _two_periods(by_year, key):
    years=by_year['Year'].sort_values().unique().tolist()
    midpoint=len(years)//2
    # Period selector preserves useful default even for sparse years
    first_end=st.select_slider('End of earlier period', options=years[:-1],
                               value=years[max(0,midpoint-1)],key=f'{key}_split')
    return by_year[by_year.Year<=first_end],by_year[by_year.Year>first_end],first_end


def render_investigation(df: pd.DataFrame, finding: dict, option: dict, key: str):
    """Render controls for a chosen question; return (explanation, Plotly figure)."""
    r=finding['recipe']; ident=option['id']; kind=r['type']
    if kind=='time':
        data=_date_frame(df,r); date,value=r['date'],r['value']
        default='Total' if any(word in value.lower() for word in ['snowfall','sales','revenue','rainfall','precipitation','count']) else 'Average'
        method, method_label=_aggregation_ui(key,default)
        # Annual comparisons from monthly datasets should not treat incomplete years
        # as if they represented 12 months of observations.
        monthly_data = _monthly_enough(data, date)
        complete_year_note = ''
        if monthly_data and ident in ('smoothing','decades','earlier_later','year_variation'):
            completeness = data.assign(Year=data[date].dt.year,Month=data[date].dt.month)\
                               .groupby('Year')['Month'].nunique()
            valid_years = completeness[completeness == 12].index
            complete_year_note = f' Annual comparisons omit {len(completeness)-len(valid_years)} year(s) with fewer than 12 represented calendar months.'
            annual_data = data[data[date].dt.year.isin(valid_years)]
        else:
            annual_data = data
        annual=_yearly(annual_data,date,value,method)
        if ident=='smoothing':
            period=st.selectbox('View observations by',['Year','As recorded'],key=f'{key}_period')
            series=(annual.rename(columns={'Year':'Period'}) if period=='Year' else
                    data.groupby(date,as_index=False)[value].agg(method).rename(columns={date:'Period'}))
            if len(series)<3:
                st.info('At least three time points are needed for smoothing.');return None
            window=st.slider('Periods in moving average',2,min(20,len(series)),min(5,len(series)),key=f'{key}_smooth')
            series['Moving average']=series[value].rolling(window,min_periods=window).mean()
            fig=px.line(series,x='Period',y=[value,'Moving average'], title=f'{value}: values and {window}-period moving average')
            explanation=(f'The {window}-period moving average smooths fluctuations. The chart uses {method_label.lower()} '
                         'values within periods; smoothing does not prove a statistically significant trend.' + complete_year_note)
        elif ident=='decades':
            annual['Decade']=(annual.Year//10)*10
            decade=annual.groupby('Decade').agg(Average_year=(value,'mean'),
                                                 Years=('Year','nunique'),
                                                 Median_year=(value,'median')).reset_index()
            decade['Decade']=decade['Decade'].astype(str)+'s'
            fig=px.bar(decade,x='Decade',y='Average_year',hover_data=['Years','Median_year'],
                       title=f'Average annual {method_label.lower()} of {value} by decade',
                       labels={'Average_year':f'Average of yearly {method_label.lower()} {value}'})
            explanation=('Each year is summarized first, then the yearly values are averaged within a decade. '
                         f'The decades contain {int(decade.Years.min())}–{int(decade.Years.max())} years in this selection; '
                         'partial decades should not be mistaken for full 10-year comparisons. '
                         'Totals should be used only for additive measures.' + complete_year_note)
        elif ident=='earlier_later':
            early,late,cut=_two_periods(annual,key)
            if early.empty or late.empty: return None
            summary=pd.DataFrame({'Period':[f'Through {cut}',f'After {cut}'],
                                  'Value':[early[value].mean(),late[value].mean()],
                                  'Years':[len(early),len(late)]})
            fig=px.bar(summary,x='Period',y='Value',hover_data=['Years'],
                       title=f'Earlier vs recent annual {method_label.lower()} of {value}')
            explanation=(f'The earlier period averages {summary.Value.iloc[0]:,.2f} across {len(early)} years; '
                         f'the later period averages {summary.Value.iloc[1]:,.2f} across {len(late)} years. '
                         'Adjust the split to see whether the comparison is sensitive to your timeframe. '
                         'This is descriptive, not a test of statistical significance.' + complete_year_note)
        elif ident=='months':
            annual_yrs=sorted(data[date].dt.year.unique())
            split=st.select_slider('Last year of the earlier period', options=annual_yrs[:-1],
                                   value=annual_yrs[max(0,len(annual_yrs)//2-1)],key=f'{key}_split')
            frame=data.assign(Year=data[date].dt.year,Month=data[date].dt.month,
                              Period=np.where(data[date].dt.year<=split,f'Through {split}',f'After {split}'))
            # Aggregate first within year/month so months with multiple rows aren't overweighted.
            per_month=frame.groupby(['Year','Month','Period'],as_index=False)[value].agg(method)
            monthly=per_month.groupby(['Month','Period'],as_index=False)[value].mean()
            fig=px.line(monthly,x='Month',y=value,color='Period',markers=True,
                        title=f'How the monthly profile of {value} changed',
                        labels={value:f'Average yearly monthly {method_label.lower()} of {value}'})
            fig.update_xaxes(tickmode='array',tickvals=list(range(1,13)),
                             ticktext=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
            explanation=('Each year/month is summarized first, then monthly values are averaged within each period. '
                         'This shows which calendar months differ, not why they differ. '
                         'Incomplete years or months may affect comparisons.')
        elif ident=='early_late':
            frame=data.assign(Year=data[date].dt.year,Month=data[date].dt.month)
            month_start=st.selectbox('Define the first part of a year as', ['January–March','January–June'],key=f'{key}_months')
            cutoff=3 if month_start=='January–March' else 6
            per_month=frame.groupby(['Year','Month'],as_index=False)[value].agg(method)
            per_month['Early']=per_month['Month']<=cutoff
            counts=per_month.groupby('Year').agg(early_months=('Early','sum'),months=('Month','nunique'))
            qualified=counts[(counts.early_months>=cutoff) & (counts.months==12)].index
            per_month=per_month[per_month.Year.isin(qualified)]
            summary=per_month.groupby(['Year','Early'])[value].sum().unstack()
            if summary.empty or len(summary)<5 or True not in summary or False not in summary:
                st.info('Not enough sufficiently complete years for this comparison.');return None
            summary=summary.rename(columns={True:'Early-year total',False:'Rest-of-year total'}).reset_index()
            fig=px.scatter(summary,x='Early-year total',y='Rest-of-year total',hover_data=['Year'],
                           title=f'First part of year vs remaining part: {value}')
            correlation=summary['Early-year total'].corr(summary['Rest-of-year total'])
            explanation=(f'Using {len(summary)} years with all twelve calendar months represented, the correlation between '
                         f'early- and rest-of-year sums is {correlation:+.2f}. This is meaningful only if values '
                         'are additive; for rates and temperatures, use a different analysis. '
                         'Calendar years may not align with ski seasons or other real-world cycles.')
        elif ident=='year_variation':
            top=annual.nlargest(min(6,len(annual)),value).assign(Type='High')
            bottom=annual.nsmallest(min(6,len(annual)),value).assign(Type='Low')
            extremes=pd.concat([top,bottom]).drop_duplicates('Year').sort_values('Year')
            fig=px.bar(extremes,x='Year',y=value,color='Type',title='Most extreme years in this period')
            explanation='Extreme years provide context for the overall pattern, but cannot by themselves establish a long-term shift.' + complete_year_note
        else:return None
        return explanation,_style(fig)

    if kind=='groups':
        cat,val=r['category'],r['value']; data=df[[cat,val]].dropna()
        if ident=='group_spread':
            fig=px.box(data,x=cat,y=val,points='outliers',title=f'Spread of {val} within {cat}')
            note='The median, quartiles, and potential outliers show how much a group average can hide.'
        elif ident=='group_method':
            method,word=_aggregation_ui(key)
            summary=data.groupby(cat,observed=True,as_index=False)[val].agg(method).sort_values(val,ascending=False)
            fig=px.bar(summary,x=cat,y=val,title=f'{word} {val} by {cat}')
            note='Switch calculations to see whether the ranking changes. Totals are influenced by group sizes and may not suit rates.'
        elif ident=='group_size':
            summary=data.groupby(cat,observed=True).size().rename('Count').reset_index()
            fig=px.bar(summary,x=cat,y='Count',title='Usable observations per group')
            note='Unequal group sizes can make differences more difficult to interpret and can influence totals.'
        else:return None
        return note,_style(fig)

    if kind=='distribution':
        val=r['value']; numbers=df[val].dropna();q1,q3=numbers.quantile([.25,.75]);iqr=q3-q1
        if ident=='outliers':
            low,high=q1-1.5*iqr,q3+1.5*iqr
            frame=df[[val]].copy();frame['Flag']=np.where((frame[val]<low)|(frame[val]>high),'Outside fence','Within fence')
            fig=px.histogram(frame,x=val,color='Flag',nbins=35,title=f'Potential extremes of {val}')
            count=int((frame.Flag=='Outside fence').sum())
            note=f'{count:,} observations lie outside 1.5×IQR fences ({low:,.2f} to {high:,.2f}). They are not necessarily errors.'
        elif ident=='quantiles':
            fig=px.box(df,y=val,points='outliers',title=f'Middle range and extremes of {val}')
            note=f'The middle 50% of recorded values lies between {q1:,.2f} and {q3:,.2f}.'
        elif ident=='dist_time':
            dates=df.select_dtypes(include='datetime').columns.tolist();d=dates[0]
            frame=df[[d,val]].dropna().copy();frame['Year']=frame[d].dt.year
            years=sorted(frame.Year.unique());cut=years[max(0,len(years)//2-1)]
            frame['Period']=np.where(frame.Year<=cut,f'Through {cut}',f'After {cut}')
            fig=px.box(frame,x='Period',y=val,points='outliers',title=f'Did the spread of {val} shift?')
            note='Compare medians and the middle half of observations. The two periods may contain different numbers of measurements.'
        elif ident=='dist_relation':
            other=[c for c in df.select_dtypes(include='number').columns if c!=val and df[c].nunique(dropna=True)>=4]
            if not other:return None
            x=st.selectbox('Compare with',other,key=f'{key}_other')
            fig=px.scatter(df.head(5000),x=x,y=val,title=f'{val} vs {x}')
            note='Patterns between variables are associations, not proof of cause and effect.'
        else:return None
        return note,_style(fig)

    if kind=='relationship':
        x,y=r['x'],r['y'];data=df[[x,y]].dropna().copy()
        if ident=='trim':
            pct=st.slider('Exclude this percentage from each end of each variable',0,10,0,key=f'{key}_trim')
            if pct:
                for col in [x,y]:
                    a,b=data[col].quantile([pct/100,1-pct/100]);data=data[data[col].between(a,b)]
            r_value=data[x].corr(data[y]) if len(data)>2 else np.nan
            fig=px.scatter(data.head(5000),x=x,y=y,title=f'{x} vs {y}, Pearson r = {r_value:.2f}')
            note='Filtering extreme values changes the sample. It does not necessarily improve validity.'
        elif ident=='relationship_groups':
            cats=[c for c in df.columns if c not in [x,y] and not pd.api.types.is_numeric_dtype(df[c]) and 2<=df[c].nunique(dropna=True)<=12]
            if not cats:
                st.info('This dataset has no suitable category for splitting the comparison.');return None
            cat=st.selectbox('Group by',cats,key=f'{key}_cat')
            fig=px.scatter(df[[x,y,cat]].dropna().head(5000),x=x,y=y,color=cat,title=f'{x} vs {y} by {cat}')
            note='An overall association may be weaker, stronger, or reversed within groups.'
        elif ident=='relationship_rank':
            ranked=data.rank(method='average');rho=ranked[x].corr(ranked[y])
            fig=px.scatter(ranked.head(5000),x=x,y=y,title=f'Rank association (Spearman rho = {rho:+.2f})')
            note='Rank relationships can reveal monotonic patterns that differ from a straight-line association. Correlation is not causation.'
        else:return None
        return note,_style(fig)

    if kind=='quality':
        if ident=='missing':
            summary=df.isna().sum().rename('Missing values').reset_index();summary.columns=['Column','Missing values']
            fig=px.bar(summary,x='Column',y='Missing values',title='Missing observations by column')
            note='Missing values may not be random, and a blank might mean not applicable rather than unknown.'
        elif ident=='missing_time':
            dates=df.select_dtypes(include='datetime').columns.tolist()
            if not dates:return None
            d=dates[0]; frame=df.copy();frame['Year']=frame[d].dt.year
            frame['Missing cells']=df.isna().sum(axis=1)
            summary=frame.groupby('Year',as_index=False)['Missing cells'].mean()
            fig=px.line(summary,x='Year',y='Missing cells',markers=True,title='Average missing cells per row by year')
            note='Different numbers of rows in each year may affect these averages. This does not identify the cause of missingness.'
        else:return None
        return note,_style(fig)
    return None


def investigate(df:pd.DataFrame,finding:dict,key:str):
    """Streamlit wrapper returning (question, explanation, figure), if supported."""
    options=suggest_followups(df,finding)
    if not options:
        st.info('There is not enough suitable data for a reliable follow-up question here.')
        return None
    lanes=[lane for lane in LANES if any(o['lane']==lane for o in options)]
    lane=st.radio('Choose a way to look at this finding',lanes,horizontal=True,key=f'{key}_lane')
    selected=[o for o in options if o['lane']==lane]
    questions={o['id']:o['question'] for o in selected}
    choice=st.selectbox('What would you like to investigate?',list(questions),format_func=lambda i:questions[i],key=f'{key}_question')
    selected_option=next(o for o in selected if o['id']==choice)
    output=render_investigation(df,finding,selected_option,f'{key}_{choice}')
    if output is None:return None
    note,fig=output
    return selected_option['question'],note,fig
