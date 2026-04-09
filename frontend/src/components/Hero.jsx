import { MapPin, Clock, CalendarIcon as CalendarRange, User, ArrowUpRight } from 'lucide-react';
import dayjs from 'dayjs';
import { getRelevanceScore, getActivityCampus } from '../api';

export default function Hero({ activities = [], onActivityClick, selectedCollege = 'all' }) {
  const rankedActivities = [...activities].sort((a, b) => {
    const scoreA = (typeof a.student_score === 'number' ? a.student_score : getRelevanceScore(a, selectedCollege));
    const scoreB = (typeof b.student_score === 'number' ? b.student_score : getRelevanceScore(b, selectedCollege));
    if (scoreA !== scoreB) return scoreB - scoreA;
    if ((a.days_until ?? 99) !== (b.days_until ?? 99)) return (a.days_until ?? 99) - (b.days_until ?? 99);
    return (a.activity_time || '').localeCompare(b.activity_time || '');
  });

  const main = rankedActivities[0];
  if (!main) return null;

  const dateStr = dayjs(main.activity_date).format('M月D日');
  const campus = getActivityCampus(main);

  const getGroundedCue = (activity) => {
    const today = dayjs().startOf('day');
    const target = dayjs(activity.activity_date).startOf('day');
    if (target.isSame(today, 'day')) {
      if (/(18[:：]|19[:：]|20[:：]|21[:：])/.test(activity.activity_time || '')) return '今晚学术看点';
      return '今日重磅推荐';
    }
    if (target.isSame(today.add(1, 'day'), 'day')) return '明日先睹为快';
    if (activity.registration_required) return '席位有限 · 开放报名';
    return '本周学术精选';
  };

  const hasCover = Boolean(main.cover_image);

  return (
    <section className="hero-section">
      <div
        className="hero-highlight"
        onClick={() => onActivityClick?.(main)}
        style={{
          background: hasCover
            ? `linear-gradient(to right, rgba(78,74,69,0.82) 0%, rgba(78,74,69,0.55) 100%), url(${main.cover_image}) center/cover`
            : 'var(--morandi-blue)'
        }}
      >
        <div className="hero-subtitle">
          {getGroundedCue(main)}
        </div>
        <h1 className="hero-title">{main.title}</h1>

        <div className="hero-meta">
          <span>
            <MapPin size={16} />
            {campus ? `${campus}校区 · ` : ''}{main.location || '地点请查看详情'}
          </span>
          <span>
            <Clock size={16} />
            {main.activity_time || '时间待确定'}
          </span>
          <span>
            <CalendarRange size={16} />
            {dateStr}
          </span>
          {main.speaker && (
            <span>
              <User size={16} />
              {main.speaker}
            </span>
          )}
        </div>

        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{
            padding: '0.35rem 0.85rem',
            fontSize: '0.8rem',
            fontWeight: 600,
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(255,255,255,0.2)',
            color: 'white'
          }}>
            {main.college_name}
          </span>
          {main.registration_required && (
            <span style={{
              padding: '0.35rem 0.85rem',
              fontSize: '0.8rem',
              fontWeight: 600,
              borderRadius: 'var(--radius-sm)',
              background: 'var(--morandi-pink)',
              color: 'white'
            }}>
              需提前报名
            </span>
          )}
          <span style={{
            padding: '0.35rem 0.85rem',
            fontSize: '0.8rem',
            fontWeight: 500,
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(255,255,255,0.15)',
            color: 'white',
            display: 'flex',
            alignItems: 'center',
            gap: '0.3rem'
          }}>
            查看详情
            <ArrowUpRight size={14} />
          </span>
        </div>
      </div>
    </section>
  );
}
