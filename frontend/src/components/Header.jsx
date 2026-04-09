import { useEffect, useRef } from 'react';
import { Search, Sun, Moon, Command } from 'lucide-react';

export default function Header({
  searchQuery,
  onSearchChange,
  theme,
  onThemeToggle
}) {
  const searchInputRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <header className="header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--morandi-blue)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: '1rem',
          fontWeight: 700
        }}>浙</div>
        <div>
          <div style={{
            fontSize: '0.95rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            letterSpacing: '-0.01em',
            lineHeight: 1.2
          }}>ZJU Academic</div>
          <div style={{
            fontSize: '0.7rem',
            fontWeight: 500,
            color: 'var(--text-muted)',
            letterSpacing: '0.02em'
          }}>Activity Calendar</div>
        </div>
      </div>

      <div className="header-actions" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div className="search-bar" style={{ position: 'relative' }}>
          <Search
            size={16}
            style={{
              position: 'absolute',
              left: '0.875rem',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-muted)',
              pointerEvents: 'none'
            }}
          />
          <input
            ref={searchInputRef}
            type="text"
            className="search-input"
            style={{
              width: '320px',
              paddingLeft: '2.5rem',
              paddingRight: '2.5rem',
              height: '38px',
              fontSize: '0.85rem',
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              transition: 'all var(--transition-fast)'
            }}
            placeholder="搜索讲座、报告人、学院..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
          <div style={{
            position: 'absolute',
            right: '0.625rem',
            top: '50%',
            transform: 'translateY(-50%)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.2rem',
            padding: '0.15rem 0.4rem',
            background: 'var(--bg-primary)',
            borderRadius: '4px',
            fontSize: '0.6rem',
            fontWeight: 600,
            color: 'var(--text-muted)',
            border: '1px solid var(--border)',
            pointerEvents: 'none'
          }}>
            <Command size={9} />
            <span>K</span>
          </div>
        </div>

        <button
          onClick={onThemeToggle}
          style={{
            width: '38px',
            height: '38px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid var(--border)',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            transition: 'all var(--transition-fast)',
            color: 'var(--text-secondary)'
          }}
        >
          {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
        </button>
      </div>
    </header>
  );
}
