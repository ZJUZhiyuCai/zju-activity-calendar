import dayjs from 'dayjs';
import { Calendar, Zap, LayoutGrid, CheckCircle } from 'lucide-react';

export default function StatsCards({ activities = [] }) {
  const today = dayjs().startOf('day');
  const tomorrow = today.add(1, 'day');
  const weekEnd = today.add(6, 'day');

  const stats = {
    today: activities.filter((a) => dayjs(a.activity_date).isSame(today, 'day')).length,
    tomorrow: activities.filter((a) => dayjs(a.activity_date).isSame(tomorrow, 'day')).length,
    thisWeek: activities.filter((a) => {
      const t = dayjs(a.activity_date).startOf('day');
      return t.isAfter(today.subtract(1, 'day')) && t.isBefore(weekEnd.add(1, 'day'));
    }).length,
    complete: activities.filter((a) => a.activity_time && a.location).length,
  };

  const cards = [
    { icon: Zap, value: stats.today, label: '今天看点', accent: 'var(--morandi-blue)' },
    { icon: Calendar, value: stats.tomorrow, label: '明日抢位', accent: 'var(--morandi-green)' },
    { icon: LayoutGrid, value: stats.thisWeek, label: '本周学术', accent: 'var(--morandi-brown)' },
    { icon: CheckCircle, value: stats.complete, label: '信息完整', accent: 'var(--morandi-pink)' },
  ];

  return (
    <div className="stats-row">
      {cards.map((card, index) => (
        <div key={index} className="stat-card">
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-tertiary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 0.75rem',
            color: card.accent
          }}>
            <card.icon size={16} />
          </div>
          <div className="stat-value">{card.value}</div>
          <div className="stat-label">{card.label}</div>
        </div>
      ))}
    </div>
  );
}
