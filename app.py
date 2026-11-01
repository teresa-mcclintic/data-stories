"""Data Stories: approachable, evidence-first CSV discovery (Streamlit)."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_engine import discover, fmt, load_csv, plot_finding, profile
from investigate import investigate

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Data Stories', page_icon='📊', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
html, body, [class*="css"] {font-family: Arial, Helvetica, sans-serif;}
.block-container {padding-top: 2rem;max-width: 1160px;}
h1,h2,h3 {letter-spacing: -.025em;}
[data-testid="stMetric"] {background:#f3f6fa;padding:14px;border-radius:12px;}
</style>''', unsafe_allow_html=True)


def choose_data() -> tuple[bytes | None, str]:
    st.sidebar.title('Data Stories')
    st.sidebar.caption('You bring the data. Discover its story.')
    choice = st.sidebar.radio('Start with', ['Upload my CSV', 'Explore a sample'], label_visibility='collapsed')
    if choice == 'Upload my CSV':
        up = st.sidebar.file_uploader('Choose a CSV file', type=['csv'], help='CSV files up to 8 MB')
        return (up.getvalue(), up.name) if up is not None else (None, '')
    demos = {'Mt. Bachelor monthly snowfall': 'mt_bachelor_monthly.csv', 'Fictional community survey': 'sample_survey.csv'}
    selected = st.sidebar.selectbox('Sample dataset', list(demos))
    target = ROOT / 'samples' / demos[selected]
    return target.read_bytes(), selected


def story_download(story: list[dict], source: str) -> str:
    cards=[]
    for entry in story:
        caption=html.escape(entry['title'])
        desc=html.escape(entry['summary'])
        evidence=html.escape(entry['evidence'])
        cards.append(f'<section><h2>{caption}</h2><p>{desc}</p><p><small>{evidence}</small></p>{entry["chart"]}</section>')
    return ('<!doctype html><html><head><meta charset="utf-8"><title>My Data Story</title>'
            '<style>body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:36px auto;padding:0 20px;color:#243247}'
            'section{padding:24px 0;border-top:1px solid #ddd}h1{color:#193457}small{color:#536278}</style></head><body>'
            f'<h1>My Data Story</h1><p>Source: {html.escape(source)}</p>'
            '<p>Findings are descriptive and based on the data supplied, not explanations of causation.</p>'
            + ''.join(cards) + '</body></html>')

raw, source_name = choose_data()
st.title('Discover the story in your data')
st.write('Upload a CSV to see patterns worth exploring, then investigate them with interactive charts. No spreadsheet skills needed.')

if raw is None:
    st.info('Choose **Upload my CSV** in the sidebar, or switch to **Explore a sample** to try it now.')
    st.stop()

try:
    df = load_csv(raw)
except (ValueError, pd.errors.EmptyDataError, UnicodeError) as exc:
    st.error(f'We could not open that file: {exc}')
    st.stop()

# Prevent findings from an earlier uploaded dataset appearing in a new story.
identity = (source_name, len(raw), __import__('hashlib').sha256(raw).hexdigest())
if st.session_state.get('data_identity') != identity:
    st.session_state.data_identity = identity
    st.session_state.story = []
    st.session_state.investigation_notes = {}

p = profile(df)
st.caption(f'Dataset: **{source_name}** · CSV is processed in the running app. No account or database is used.')

with st.expander('About this dataset and its limitations', expanded=False):
    st.write('This tool describes patterns and associations; it cannot establish causes, verify the accuracy of source measurements, or guarantee statistical significance.')
    st.write('Each row is treated as one observation. Repeated measurements or category totals may need additional context. Numeric group comparisons use means.')
    if 'snowfall' in source_name.lower() or 'bachelor' in source_name.lower():
        st.write('The sample Mt. Bachelor records are modeled Open-Meteo snowfall estimates, not official resort measurements. The final month may be incomplete.')
    st.warning('Do not upload confidential, personal, medical, student, or other protected data to a publicly hosted version without an appropriate privacy review.')

# Filters apply to both findings and free exploration.
st.sidebar.divider()
st.sidebar.subheader('Filter your view')
filtered = df.copy()
if 'coverage' in df.columns and 'partial' in df['coverage'].astype(str).str.lower().unique():
    include_partial = st.sidebar.checkbox('Include partial periods',value=False,help='Incomplete months can mislead comparisons with full months.')
    if not include_partial:
        filtered=filtered[filtered['coverage'].astype(str).str.lower()!='partial']
if p['dates']:
    date_col = st.sidebar.selectbox('Date field', p['dates'], key='date_filter_col')
    vals = df[date_col].dropna()
    if len(vals) and vals.min() < vals.max():
        earliest, latest = vals.min().date(), vals.max().date()
        span = st.sidebar.date_input('Date range', (earliest, latest), min_value=earliest, max_value=latest)
        if isinstance(span, (tuple,list)) and len(span)==2:
            filtered = filtered[filtered[date_col].between(pd.Timestamp(span[0]),pd.Timestamp(span[1])+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))]
if p['categories']:
    category = st.sidebar.selectbox('Optional category filter', ['No category filter']+p['categories'])
    if category != 'No category filter':
        options = sorted(df[category].dropna().astype(str).unique().tolist())
        chosen=st.sidebar.multiselect('Include categories',options,default=options)
        filtered=filtered[filtered[category].astype(str).isin(chosen)]
if filtered.empty:
    st.warning('No records match your filters. Try widening your date range or selecting more categories.')
    st.stop()

nfiltered=profile(filtered)
tabs=st.tabs(['Discover','Explore','My Data Story','Data & quality'])

with tabs[0]:
    st.subheader('What stands out?')
    st.write('These are calculated observations and promising questions—not automatically proven explanations. Filters in the sidebar update the results. In **Investigate further**, try Dig deeper, Change perspective, or Make connections.')
    a,b,c=st.columns(3)
    a.metric('Records in view', f'{len(filtered):,}')
    b.metric('Numeric fields', len(nfiltered['numeric']))
    c.metric('Missing cells',f'{nfiltered["missing"]:,}')
    findings=discover(filtered,limit=5)
    if not findings:
        st.info('This dataset has too little usable numeric data for automated findings. Try the Explore tab or check the CSV format.')
    for idx,f in enumerate(findings):
        with st.container(border=True):
            st.markdown(f'### {idx+1}. {f["title"]}')
            st.write(f['summary'])
            st.caption(f['evidence'])
            st.plotly_chart(plot_finding(filtered,f),use_container_width=True,key=f'auto_{idx}')
            with st.expander('A question worth asking'):
                st.write(f['question'])
            with st.expander('🔎 Investigate further — three ways to explore'):
                result = investigate(filtered, f, key=f'inv_{idx}')
                if result is not None:
                    question, explanation, followup_fig = result
                    st.plotly_chart(followup_fig, use_container_width=True, key=f'followup_chart_{idx}')
                    st.caption(explanation)
                    st.markdown('**What do you notice?**')
                    note = st.text_area('Write a note to include in your Data Story (optional)',
                                        key=f'investigation_note_{idx}',height=80)
                    if st.button('Save this investigation to My Data Story', key=f'save_followup_{idx}'):
                        ident=('investigation', question, f['title'])
                        if any(entry.get('ident') == ident for entry in st.session_state.story):
                            st.info('This investigation is already in your story. Remove it there to save a different version.')
                        else:
                            st.session_state.story.append({
                                'ident': ident,
                                'title': question,
                                'summary': f'Follow-up to: {f["title"]}' + (f' — {note}' if note.strip() else ''),
                                'evidence': explanation,
                                'chart': followup_fig.to_html(full_html=False,include_plotlyjs=False)
                            })
                            st.success('Investigation added to My Data Story.')
            if st.button('Save to My Data Story',key=f'save_{idx}'):
                ident=(f['title'],f['summary'])
                if any((s['title'],s['summary'])==ident for s in st.session_state.story):
                    st.info('This finding is already in your story.')
                else:
                    fig=plot_finding(filtered,f)
                    st.session_state.story.append({**f,'chart':fig.to_html(full_html=False,include_plotlyjs=False)})
                    st.success('Added to My Data Story.')

with tabs[1]:
    st.subheader('Explore your own question')
    st.write('Choose what you want to investigate. The app will make a suitable interactive chart.')
    chart_type=st.selectbox('I want to…',['See how something changes over time','Compare groups','Understand a distribution','See whether two measures are related'])
    nums=nfiltered['numeric']
    if chart_type.startswith('See how'):
        if nfiltered['dates'] and nums:
            date=st.selectbox('Date column',nfiltered['dates'],key='explore_date')
            value=st.selectbox('Value to follow',nums,key='explore_time_value')
            aggregation=st.selectbox('When dates repeat, calculate', ['Average','Total','Median'], help='Choose Total only for additive quantities such as sales or snowfall, not temperatures or percentages.')
            grouped=filtered[[date,value]].dropna().groupby(date,as_index=False)[value].agg({'Average':'mean','Total':'sum','Median':'median'}[aggregation]).sort_values(date)
            fig=px.line(grouped,x=date,y=value,markers=True,title=f'{aggregation} {value} over time')
        else:
            st.info('This view needs a recognizable date column and a numeric column. Dates like 2024-01-01 are supported.')
            fig=None
    elif chart_type=='Compare groups':
        if nfiltered['categories'] and nums:
            cat=st.selectbox('Group by',nfiltered['categories'])
            val=st.selectbox('Compare which number?',nums)
            measure=st.radio('Calculate', ['Average','Total','Count'],horizontal=True)
            grouped=filtered.groupby(cat,as_index=False,observed=True)[val].agg({'Average':'mean','Total':'sum','Count':'count'}[measure]).sort_values(val,ascending=False)
            fig=px.bar(grouped,x=cat,y=val,title=f'{measure} of {val} by {cat}')
        else:
            st.info('This view needs a category column and a numeric column.')
            fig=None
    elif chart_type=='Understand a distribution':
        if nums:
            val=st.selectbox('Which numeric field?',nums,key='hist_val')
            bins=st.slider('Number of histogram bins',5,60,25)
            fig=px.histogram(filtered,x=val,nbins=bins,title=f'How is {val} distributed?')
        else:
            st.info('This view needs a numeric column.')
            fig=None
    else:
        if len(nums)>=2:
            x=st.selectbox('First measure',nums)
            y=st.selectbox('Second measure',[n for n in nums if n!=x])
            fig=px.scatter(filtered.head(10000),x=x,y=y,title=f'{x} compared with {y}')
            st.caption('A relationship on a chart does not establish cause and effect. Scatterplots show at most 10,000 records.')
        else:
            st.info('This view needs at least two numeric columns.')
            fig=None
    if fig is not None:
        fig.update_layout(template='plotly_white',font_family='Arial')
        st.plotly_chart(fig,use_container_width=True,key='explore_chart')
        st.download_button('Download interactive chart (HTML)',fig.to_html(full_html=True,include_plotlyjs=True).encode('utf-8'), 'data-stories-chart.html','text/html')

with tabs[2]:
    st.subheader('My Data Story')
    st.write('Collect discoveries and follow-up investigations here, then download a self-contained HTML report with interactive charts. The story is held in this browser session only.')
    story=st.session_state.story
    if not story:
        st.info('Nothing saved yet. Open Discover and save a finding or a follow-up investigation.')
    else:
        for i, item in enumerate(story):
            a,b=st.columns([5,1])
            a.markdown(f'**{i+1}. {item["title"]}**')
            a.write(item['summary'])
            if b.button('Remove',key=f'remove_{i}'):
                st.session_state.story.pop(i)
                st.rerun()
        report=story_download(story,source_name)
        # Include Plotly JS exactly once so report works offline.
        from plotly.offline import get_plotlyjs
        report=report.replace('</head>',f'<script>{get_plotlyjs()}</script></head>')
        st.download_button('Download my interactive Data Story (HTML)',report.encode('utf-8'),file_name='my_data_story.html',mime='text/html')
        if st.button('Clear my story'):
            st.session_state.story=[]
            st.rerun()

with tabs[3]:
    st.subheader('Understand your dataset')
    st.write('Inspect the original columns and look for issues before drawing conclusions.')
    st.dataframe(filtered.head(100),use_container_width=True,hide_index=True)
    st.caption('Preview shows up to 100 rows after filtering.')
    col1,col2,col3=st.columns(3)
    col1.metric('Rows',f'{len(filtered):,}')
    col2.metric('Columns',filtered.shape[1])
    col3.metric('Duplicate rows',f'{nfiltered["duplicate_rows"]:,}')
    st.markdown('#### Missing values by column')
    missing=filtered.isna().sum().sort_values(ascending=False).rename('Missing values')
    st.dataframe(missing.to_frame(),use_container_width=True)
    if nfiltered['numeric']:
        st.markdown('#### Numeric summary')
        st.dataframe(filtered[nfiltered['numeric']].describe().T.round(2),use_container_width=True)
    st.download_button('Download filtered data (CSV)',filtered.to_csv(index=False).encode('utf-8'),file_name='filtered_data.csv',mime='text/csv')

st.divider()
st.caption('Data Stories v4 · Rule-based discovery and follow-up investigations · No AI API · Associations do not establish causation.')
