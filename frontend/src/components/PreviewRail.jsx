import { useMemo } from 'react';
import { Clock3, MapPin, Zap } from 'lucide-react';
import dayjs from 'dayjs';
import { getActivityCampus, getRelevanceScore, formatPreviewDate } from '../api';

const PREVIEW_MODES = [
  { id: 'relevant', label: '推荐' },
  { id: 'today', label: '今天' },
  { id: 'tomorrow', label: '明天' },
  { id: 'week', label: '本周' },
];

function buildPreviewInsights(items) {
  const today = dayjs().startOf('day');
  const completeCount = items.filter((a) => a.activity_time && a.location).length;
  const campusKnownCount = items.filter((a) => Boolean(getActivityCampus(a))).length;
  const soonCount = items.filter((a) => {
    const target = dayjs(a.activity_date).startOf('day');
    return target.isAfter(today.subtract(1, 'day')) && target.isBefore(today.add(3, 'day'));
  }).length;
  return [
    { label: '近期看点', value: soonCount, hint: '48h内' },
    { label: '信息完整', value: completeCount, hint: '时间地点明确' },
    { label: '校区已知', value: campusKnownCount, hint: '方便决策' },
  ];
}

function filterByMode(activities, mode, selectedDate) {
  const today = dayjs().startOf('day');
  const tomorrow = today.add(1, 'day');
  const weekEnd = today.add(6, 'day');

  if (mode === 'selected' && selectedDate)
    return activities.filter((a) => a.activity_date === selectedDate);
  if (mode === 'today')
    return activities.filter((a) => dayjs(a.activity_date).isSame(today, 'day'));
  if (mode === 'tomorrow')
    return activities.filter((a) => dayjs(a.activity_date).isSame(tomorrow, 'day'));
  if (mode === 'week')
    return activities.filter((a) => {
      const t = dayjs(a.activity_date).startOf('day');
      return t.isAfter(today.subtract(1, 'day')) && t.isBefore(weekEnd.add(1, 'day'));
    });
  return activities.filter((a) => dayjs(a.activity_date).startOf('day').isAfter(today.subtract(1, 'day')));
}

function sortPreviewItems(items, mode, selectedCollege) {
  const sorted = [...items];
  sorted.sort((a, b) => {
    if (mode === 'relevant') {
      const scoreA = typeof a.student_score === 'number' ? a.student_score : getRelevanceScore(a, selectedCollege);
      const scoreB = typeof b.student_score === 'number' ? b.student_score : getRelevanceScore(b, selectedCollege);
      if (scoreA !== scoreB) return scoreB - scoreA;
      if (a.activity_date !== b.activity_date) return a.activity_date.localeCompare(b.activity_date);
      return (a.activity_time || '').localeCompare(b.activity_time || '');
    }
    if (a.activity_date !== b.activity_date) return a.activity_date.localeCompare(b.activity_date);
    return (a.activity_time || '').localeCompare(b.activity_time || '');
  });
  return sorted;
}

export default function PreviewRail({
  activities = [],
  selectedDate,
  previewMode = 'relevant',
  onPreviewModeChange,
  onActivityClick,
  selectedCollege = 'all',
}) {
  const scopedActivities = useMemo(() => filterByMode(activities, previewMode, selectedDate), [activities, previewMode, selectedDate]);
  const previewItems = useMemo(() => sortPreviewItems(scopedActivities, previewMode, selectedCollege).slice(0, 10), [scopedActivities, previewMode, selectedCollege]);
  const previewInsights = useMemo(() => buildPreviewInsights(scopedActivities), [scopedActivities]);

  const leadActivity = previewItems[0];
  const listItems = previewItems.slice(1);
  const totalScoped = scopedActivities.length;

  const heading = previewMode === 'selected' && selectedDate
    ? `${dayjs(selectedDate).format('M月D日')} 行程`
    : '学术导览';

  const summary = previewMode === 'selected' && selectedDate
    ? `该日期共 ${totalScoped} 项活动`
    : `当前共 ${totalScoped} 项活动`;

  return (
    <aside className="preview-rail">
      <div className="preview-panel">
        <div className="preview-hero">
          <div className="preview-kicker">
            <Zap size={12} />
            学术发现
          </div>
          <h3 className="preview-title">{heading}</h3>
          <p className="preview-copy">{summary}</p>
        </div>

        <div className="preview-mode-bar">
          {selectedDate && (
            <button
              className={`preview-mode-chip ${previewMode === 'selected' ? 'active' : ''}`}
              onClick={() => onPreviewModeChange?.('selected')}
            >
              已选日期
            </button>
          )}
          {PREVIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              className={`preview-mode-chip ${previewMode === mode.id ? 'active' : ''}`}
              onClick={() => onPreviewModeChange?.(mode.id)}
            >
              {mode.label}
            </button>
          ))}
        </div>

        <div className="preview-insights">
          {previewInsights.map((item) => (
            <div key={item.label} className="preview-insight-card">
              <div className="preview-insight-value">{item.value}</div>
              <div className="preview-insight-label">{item.label}</div>
              <div className="preview-insight-hint">{item.hint}</div>
            </div>
          ))}
        </div>

        <div style={{ padding: '0.5rem 1rem 1.5rem' }}>
          {leadActivity ? (
            <div>
              {/* Lead item */}
              <button
                className="preview-item"
                onClick={() => onActivityClick?.(leadActivity)}
                style={{
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '1.25rem',
                  border: '1px solid var(--border)',
                  marginBottom: '0.75rem',
                  borderLeft: '3px solid var(--morandi-blue)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span style={{ color: 'var(--morandi-blue-deep)', fontWeight: 600, fontSize: '0.75rem' }}>
                    {formatPreviewDate(leadActivity.activity_date)} · 精选
                  </span>
                </div>
                <div className="preview-item-title" style={{ fontSize: '1.05rem', marginBottom: '0.75rem' }}>
                  {leadActivity.title}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Clock3 size={13} /> {leadActivity.activity_time || '时间待定'}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <MapPin size={13} /> {leadActivity.location || '地点待定'}
                  </span>
                </div>
              </button>

              {/* List items */}
              {listItems.map((activity) => (
                <button
                  key={activity.id}
                  className="preview-item"
                  onClick={() => onActivityClick?.(activity)}
                  style={{ padding: '0.85rem 0', width: '100%' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                    <span style={{ color: 'var(--morandi-blue)', fontWeight: 600, fontSize: '0.7rem' }}>
                      {formatPreviewDate(activity.activity_date)}
                    </span>
                    {activity.registration_required && (
                      <span className="preview-badge" style={{ fontSize: '0.6rem', padding: '0.1rem 0.35rem' }}>需报名</span>
                    )}
                  </div>
                  <div className="preview-item-title" style={{ fontSize: '0.9rem' }}>{activity.title}</div>
                  <div style={{ marginTop: '0.3rem', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: '0.75rem' }}>
                    <span>{getActivityCampus(activity) || '校区待补'}</span>
                    <span>{activity.activity_time?.split(' ')[0] || '时间待补'}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="preview-empty">
              <div className="preview-empty-title">暂无符合条件的活动</div>
              <div className="preview-empty-copy">试试切换筛选维度或查看本周活动</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
