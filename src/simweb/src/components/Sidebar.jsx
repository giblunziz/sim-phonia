import { useState } from 'react';

const SECTIONS = [
  {
    id: 'chat',
    label: 'Chat',
    items: [{ id: 'chat', label: 'Conversation' }],
  },
  {
    id: 'jeu',
    label: 'Jeu',
    items: [{ id: 'activity-dashboard', label: 'Dashboard MJ' }],
  },
  {
    id: 'storage',
    label: 'Storage',
    items: [
      { id: 'storage-characters',  label: 'Personnages' },
      { id: 'storage-knowledge',   label: 'Knowledge' },
      { id: 'storage-activities',  label: 'Activités' },
      { id: 'storage-schemas',     label: 'Schémas' },
      { id: 'storage-scenes',      label: 'Scènes' },
      { id: 'storage-instances',   label: 'Instances' },
    ],
  },
  {
    id: 'atelier',
    label: 'Atelier',
    items: [{ id: 'tools', label: 'Tools' }],
  },
  {
    id: 'admin',
    label: 'Administration',
    items: [
      { id: 'server', label: 'Serveur' },
      { id: 'memory', label: 'Mémoire' },
    ],
  },
];

export default function Sidebar({ open, activePanel, onNavigate, onToggle }) {
  const [expanded, setExpanded] = useState({ chat: true, jeu: true, admin: true, storage: true, atelier: true });

  const toggleSection = (id) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <aside className={`sidebar ${open ? 'sidebar-open' : 'sidebar-closed'}`}>
      <button
        className="sidebar-toggle"
        onClick={onToggle}
        title={open ? 'Réduire la barre' : 'Ouvrir la barre'}
      >
        {open ? '‹' : '›'}
      </button>

      {open && (
        <nav className="sidebar-nav">
          {SECTIONS.map((section) => (
            <div key={section.id} className="accordion-section">
              <button
                className="accordion-header"
                onClick={() => toggleSection(section.id)}
              >
                <span>{section.label}</span>
                <span className="chevron">{expanded[section.id] ? '▾' : '▸'}</span>
              </button>

              {expanded[section.id] && (
                <ul className="accordion-items">
                  {section.items.map((item) => (
                    <li key={item.id}>
                      <button
                        className={`nav-item ${activePanel === item.id ? 'active' : ''}`}
                        onClick={() => onNavigate(item.id)}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </nav>
      )}
    </aside>
  );
}
