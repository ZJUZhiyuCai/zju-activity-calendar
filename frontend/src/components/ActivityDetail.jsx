import { X, Calendar, Clock, MapPin, Building2, ExternalLink, Bell } from 'lucide-react';
import dayjs from 'dayjs';
import {
  describeActivityCompleteness,
  describeActivityConfidence,
} from '../lib/activityQuality';

// Morandi-toned activity type colors
const ACTIVITY_TYPE_COLORS = {
  '讲座': { bg: 'rgba(143,160,168,0.12)', color: '#6E8490' },
  '学术报告': { bg: 'rgba(155,142,196,0.12)', color: '#8B7DB8' },
  '论坛': { bg: 'rgba(154,165,141,0.12)', color: '#7A8A6E' },
  '研讨会': { bg: 'rgba(168,146,123,0.12)', color: '#96805E' },
  '培训讲座': { bg: 'rgba(143,160,168,0.12)', color: '#6E8490' },
  '比赛': { bg: 'rgba(183,162,154,0.12)', color: '#A08478' },
  '活动': { bg: 'rgba(183,162,154,0.12)', color: '#A08478' },
  'default': { bg: 'rgba(160,154,146,0.12)', color: '#7A746C' }
};

function getTypeStyle(type) {
  return ACTIVITY_TYPE_COLORS[type] || ACTIVITY_TYPE_COLORS['default'];
}

export default function ActivityDetail({ activity, onClose }) {
  if (!activity) return null;

  const typeStyle = getTypeStyle(activity.activity_type);
  const completeness = describeActivityCompleteness(activity);
  const confidence = describeActivityConfidence(activity);

  const openSource = () => {
    if (activity.source_url) window.open(activity.source_url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className={`modal-overlay ${activity ? 'open' : ''}`} onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ flex: 1, paddingRight: '2rem' }}>
            <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1rem' }}>
              <span className="preview-badge" style={{
                backgroundColor: typeStyle.bg,
                color: typeStyle.color,
                border: `1px solid ${typeStyle.color}20`
              }}>
                {activity.activity_type || '讲座'}
              </span>
              {activity.source_type === 'core' && (
                <span className="preview-badge strong">校级官方</span>
              )}
              <span className={`preview-badge quality-${completeness.level}`}>{completeness.label}</span>
              <span className={`preview-badge quality-${confidence.level}`}>{confidence.label}</span>
            </div>
            <h3 style={{
              fontSize: '1.35rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
              lineHeight: 1.35,
              maxWidth: '440px'
            }}>{activity.title}</h3>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {/* Info Grid */}
          <div className="activity-info-grid">
            {[
              { icon: Calendar, label: '日期', value: dayjs(activity.activity_date).format('YYYY年M月D日') },
              { icon: Clock, label: '时间', value: activity.activity_time || '待补充' },
              { icon: MapPin, label: '地点', value: activity.location || '校内办公区' },
              { icon: Building2, label: '主办', value: activity.college_name },
            ].map((item) => (
              <div key={item.label} style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ color: 'var(--morandi-blue)', marginTop: '0.15rem' }}><item.icon size={18} /></div>
                <div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.03em' }}>{item.label}</div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', marginTop: '0.1rem', color: 'var(--text-primary)' }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="quality-grid">
            <div className={`quality-card ${completeness.level}`}>
              <div className="quality-card-label">字段完整度</div>
              <div className="quality-card-title">{completeness.label}</div>
              <div className="quality-card-copy">{completeness.summary}</div>
              <div className="quality-card-meta">完整度评分：{Math.round((completeness.score || 0) * 100)}%</div>
              {completeness.missingFields.length > 0 && (
                <div className="quality-card-meta">当前仍缺：{completeness.missingFields.join('、')}</div>
              )}
            </div>

            <div className={`quality-card ${confidence.level}`}>
              <div className="quality-card-label">来源置信度</div>
              <div className="quality-card-title">{confidence.label}</div>
              <div className="quality-card-copy">{confidence.summary}</div>
              <div className="quality-card-meta">置信度评分：{Math.round((confidence.score || 0) * 100)}%</div>
              {confidence.reasons.length > 0 && (
                <div className="quality-card-meta">判断依据：{confidence.reasons.join(' / ')}</div>
              )}
            </div>
          </div>

          {/* Speaker */}
          {activity.speaker && (
            <div className="speaker-card">
              <div className="speaker-avatar">{activity.speaker.charAt(0)}</div>
              <div style={{ flex: 1 }}>
                <div className="speaker-name">{activity.speaker}</div>
                {activity.speaker_title && <div className="speaker-title">{activity.speaker_title}</div>}
              </div>
            </div>
          )}

          {/* Description */}
          <div className="activity-description">
            <strong>活动内容提要</strong>
            <p>{activity.description || '本活动暂无详细介绍，请关注学院官方发布的最新信息。'}</p>
          </div>

          {activity.speaker_intro && (
            <div className="activity-description">
              <strong>主讲人简介</strong>
              <p>{activity.speaker_intro}</p>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {activity.registration_required && (
            <button
              className="btn btn-primary"
              onClick={() => window.open(activity.registration_link, '_blank', 'noopener,noreferrer')}
            >
              <Bell size={16} />
              立即报名
            </button>
          )}
          {activity.source_url && (
            <button className="btn btn-secondary" onClick={openSource}>
              <ExternalLink size={16} />
              查看原文
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
