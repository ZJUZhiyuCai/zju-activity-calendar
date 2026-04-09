import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon } from 'lucide-react';
import dayjs from 'dayjs';
import { groupActivitiesByDate, getFirstDayOfMonth, isToday, getCollegeColor } from '../api';

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
const MONTHS = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'];

export default function Calendar({
  activities = [],
  selectedDate,
  onDateSelect,
  onActivityClick
}) {
  const initialMonth = selectedDate ? dayjs(selectedDate) : dayjs();
  const [currentYear, setCurrentYear] = useState(initialMonth.year());
  const [currentMonth, setCurrentMonth] = useState(initialMonth.month() + 1);

  const activitiesByDate = useMemo(() => groupActivitiesByDate(activities), [activities]);

  const calendarDays = useMemo(() => {
    const daysInMonth = dayjs(`${currentYear}-${currentMonth}`).daysInMonth();
    const firstDayOfWeek = getFirstDayOfMonth(currentYear, currentMonth);
    const days = [];

    const prevMonth = currentMonth === 1 ? 12 : currentMonth - 1;
    const prevYear = currentMonth === 1 ? currentYear - 1 : currentYear;
    const prevMonthDays = dayjs(`${prevYear}-${prevMonth}`).daysInMonth();

    for (let i = firstDayOfWeek - 1; i >= 0; i--) {
      const day = prevMonthDays - i;
      const date = dayjs(`${prevYear}-${prevMonth}-${day}`).format('YYYY-MM-DD');
      days.push({ day, date, isCurrentMonth: false, activities: activitiesByDate[date] || [] });
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const date = dayjs(`${currentYear}-${currentMonth}-${day}`).format('YYYY-MM-DD');
      days.push({ day, date, isCurrentMonth: true, isToday: isToday(date), activities: activitiesByDate[date] || [] });
    }

    const remainingDays = 42 - days.length;
    const nextMonth = currentMonth === 12 ? 1 : currentMonth + 1;
    const nextYear = currentMonth === 12 ? currentYear + 1 : currentYear;
    for (let day = 1; day <= remainingDays; day++) {
      const date = dayjs(`${nextYear}-${nextMonth}-${day}`).format('YYYY-MM-DD');
      days.push({ day, date, isCurrentMonth: false, activities: activitiesByDate[date] || [] });
    }
    return days;
  }, [currentYear, currentMonth, activitiesByDate]);

  const prevMonth = () => {
    if (currentMonth === 1) { setCurrentMonth(12); setCurrentYear(currentYear - 1); }
    else setCurrentMonth(currentMonth - 1);
  };

  const nextMonth = () => {
    if (currentMonth === 12) { setCurrentMonth(1); setCurrentYear(currentYear + 1); }
    else setCurrentMonth(currentMonth + 1);
  };

  const goToToday = () => {
    setCurrentYear(dayjs().year());
    setCurrentMonth(dayjs().month() + 1);
    onDateSelect?.(dayjs().format('YYYY-MM-DD'));
  };

  const handleDayClick = (date, dayActivities) => {
    onDateSelect?.(date);
    if (dayActivities.length === 1) onActivityClick?.(dayActivities[0]);
  };

  // Morandi-toned college color mapping
  const getMorandiColor = (collegeName) => {
    const raw = getCollegeColor(collegeName);
    // Return a desaturated version
    return raw || 'var(--morandi-blue)';
  };

  return (
    <div style={{
      background: 'var(--bg-secondary)',
      borderRadius: 'var(--radius-xl)',
      padding: '1.5rem',
      border: '1px solid var(--border)'
    }}>
      {/* Calendar Header */}
      <div style={{
        marginBottom: '1.5rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <div style={{
            fontSize: '0.7rem',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            marginBottom: '0.25rem'
          }}>
            <CalendarIcon size={11} />
            学术日程
          </div>
          <h2 style={{
            fontSize: '1.5rem',
            color: 'var(--text-primary)',
            margin: 0,
            fontWeight: 600
          }}>
            {MONTHS[currentMonth - 1]}{' '}
            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>{currentYear}</span>
          </h2>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            background: 'var(--bg-tertiary)',
            borderRadius: 'var(--radius-md)',
            padding: '0.25rem',
            border: '1px solid var(--border)'
          }}>
            <button onClick={prevMonth} style={{
              border: 'none', background: 'transparent', padding: '0.4rem',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center'
            }}>
              <ChevronLeft size={16} />
            </button>
            <div style={{ width: '1px', height: '14px', background: 'var(--border)', margin: '0 0.25rem' }} />
            <button onClick={nextMonth} style={{
              border: 'none', background: 'transparent', padding: '0.4rem',
              borderRadius: 'var(--radius-sm)', cursor: 'pointer', color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center'
            }}>
              <ChevronRight size={16} />
            </button>
          </div>

          <button onClick={goToToday} style={{
            background: 'var(--morandi-blue)',
            color: 'white',
            border: 'none',
            padding: '0.5rem 1rem',
            borderRadius: 'var(--radius-md)',
            fontWeight: 600,
            fontSize: '0.8rem',
            cursor: 'pointer'
          }}>
            今天
          </button>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="calendar-grid">
        <div className="calendar-weekdays">
          {WEEKDAYS.map(day => (
            <div key={day} className="weekday">{day}</div>
          ))}
        </div>

        <div className="calendar-days">
          {calendarDays.map((dayInfo, index) => {
            const { day, date, isCurrentMonth, isToday: isTodayFlag, activities: dayActs } = dayInfo;
            const isSelected = selectedDate === date;

            return (
              <div
                key={index}
                className={`calendar-day ${!isCurrentMonth ? 'other-month' : ''} ${isTodayFlag ? 'today' : ''} ${isSelected ? 'selected' : ''}`}
                onClick={() => handleDayClick(date, dayActs)}
                style={{
                  background: !isCurrentMonth ? 'var(--bg-tertiary)' : undefined
                }}
              >
                <div className="day-number" style={{
                  fontWeight: isTodayFlag || isSelected ? 700 : 400,
                  color: isTodayFlag ? undefined : !isCurrentMonth ? 'var(--text-muted)' : 'var(--text-primary)'
                }}>
                  {day}
                </div>

                {dayActs.length > 0 && isCurrentMonth && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    {dayActs.slice(0, 2).map((activity, i) => (
                      <div key={i} style={{
                        fontSize: '0.65rem',
                        fontWeight: 500,
                        padding: '0.15rem 0.35rem',
                        borderRadius: '3px',
                        background: 'var(--morandi-bg-alt)',
                        color: 'var(--text-secondary)',
                        borderLeft: `2px solid ${getMorandiColor(activity.college_name)}`,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {activity.title}
                      </div>
                    ))}
                    {dayActs.length > 2 && (
                      <div style={{
                        fontSize: '0.6rem',
                        color: 'var(--text-muted)',
                        paddingLeft: '0.35rem'
                      }}>
                        +{dayActs.length - 2} 更多
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
