import { useMemo } from 'react';
import { BookOpen, Cpu, Heart, LayoutGrid, Microscope } from 'lucide-react';
import { COLLEGES } from '../api';

const CATEGORY_CONFIG = {
  'core': { name: '校园', icon: LayoutGrid },
  'humanities': { name: '人文', icon: BookOpen },
  'science': { name: '理学', icon: Microscope },
  'engineering': { name: '工学', icon: Cpu },
  'medical': { name: '医学', icon: Heart },
};

export default function CollegeFilter({
  selectedCollege,
  onCollegeSelect,
  colleges = COLLEGES,
  activities = []
}) {
  const sourceColleges = useMemo(() => {
    return Array.isArray(colleges) && colleges.length > 0 ? colleges : COLLEGES;
  }, [colleges]);

  const collegeCounts = useMemo(() => {
    const counts = { all: activities.length };
    activities.forEach(activity => {
      const collegeId = activity.college_id;
      counts[collegeId] = (counts[collegeId] || 0) + 1;
    });
    return counts;
  }, [activities]);

  const categories = useMemo(() => {
    const grouped = { core: [], humanities: [], science: [], engineering: [], medical: [] };
    sourceColleges.forEach(c => {
      if (c.id === 'all') return;
      if (grouped[c.category]) {
        if (collegeCounts[c.id] > 0 || c.category === 'core') {
          grouped[c.category].push(c);
        }
      }
    });
    return Object.entries(grouped).filter(([, items]) => items.length > 0);
  }, [sourceColleges, collegeCounts]);

  const chipStyle = (isActive) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    padding: '0.4rem 0.85rem',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid',
    borderColor: isActive ? 'var(--morandi-blue)' : 'var(--border)',
    background: isActive ? 'var(--morandi-blue)' : 'var(--bg-secondary)',
    color: isActive ? 'white' : 'var(--text-secondary)',
    fontSize: '0.8rem',
    fontWeight: isActive ? 600 : 500,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all var(--transition-fast)',
  });

  return (
    <div style={{
      padding: '0.25rem 0',
      width: '100%',
      overflowX: 'auto',
      scrollbarWidth: 'none',
      msOverflowStyle: 'none'
    }}>
      <div style={{
        display: 'flex',
        gap: '1.25rem',
        alignItems: 'center',
        padding: '0 0.25rem'
      }}>
        <button
          onClick={() => onCollegeSelect('all')}
          style={chipStyle(selectedCollege === 'all')}
        >
          <LayoutGrid size={14} />
          全部学院
          <span style={{ opacity: 0.7, fontSize: '0.7rem', fontWeight: 600 }}>
            {collegeCounts['all'] || 0}
          </span>
        </button>

        {categories.length > 0 && (
          <div style={{ width: '1px', height: '20px', background: 'var(--border)' }} />
        )}

        {categories.map(([key, items]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {key !== 'core' && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.3rem',
                fontSize: '0.65rem',
                fontWeight: 600,
                color: 'var(--text-muted)',
                letterSpacing: '0.05em',
                whiteSpace: 'nowrap'
              }}>
                {(() => { const Icon = CATEGORY_CONFIG[key].icon; return <Icon size={11} />; })()}
                {CATEGORY_CONFIG[key].name}
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.35rem' }}>
              {items.map((college) => {
                const isActive = selectedCollege === college.id;
                return (
                  <button
                    key={college.id}
                    onClick={() => onCollegeSelect(college.id)}
                    style={chipStyle(isActive)}
                  >
                    {college.name}
                    <span style={{ opacity: 0.6, fontSize: '0.7rem', fontWeight: 600 }}>
                      {collegeCounts[college.id] || 0}
                    </span>
                  </button>
                );
              })}
            </div>

            {key !== categories[categories.length - 1][0] && (
              <div style={{ width: '1px', height: '20px', background: 'var(--border)', margin: '0 0.25rem' }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
