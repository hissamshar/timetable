import { useState, useRef, useCallback, useEffect } from 'react';
import Head from 'next/head';

export default function Home() {
    const API_BASE_URL = 'https://repulsive-almire-hisamshar-2d198dbd.koyeb.app';
    const [rollNumber, setRollNumber] = useState('');
    const [timetableFile, setTimetableFile] = useState(null);
    const [datesheetFile, setDatesheetFile] = useState(null);
    const [includeExams, setIncludeExams] = useState(false);
    const [schedule, setSchedule] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [activeTab, setActiveTab] = useState('classes');
    const [syncStatus, setSyncStatus] = useState('');
    const [dragOver, setDragOver] = useState({ timetable: false, datesheet: false });
    const [faculty, setFaculty] = useState([]);
    const [metadata, setMetadata] = useState({ teachers: [], venues: [], room_aliases: {} });
    const [selectedTeacher, setSelectedTeacher] = useState(null);
    const [officialFiles, setOfficialFiles] = useState({ timetable: null, datesheet: null });
    const [useOfficial, setUseOfficial] = useState({ timetable: true, datesheet: true });
    const [academicPlan, setAcademicPlan] = useState([]);
    const [views, setViews] = useState(null);

    const timetableRef = useRef(null);
    const datesheetRef = useRef(null);

    // Load faculty data, metadata, and cached schedule on mount
    useEffect(() => {
        // Load cached schedule
        const cached = localStorage.getItem('timetable_cache');
        if (cached) {
            try {
                const data = JSON.parse(cached);
                setSchedule(data);
                if (data.roll_number) setRollNumber(data.roll_number);
            } catch (e) { localStorage.removeItem('timetable_cache'); }
        }

        const fetchWithRetry = async (url, options = {}, retries = 3, backoff = 1000) => {
            try {
                const res = await fetch(url, options);
                if (!res.ok) throw new Error(`Status ${res.status}`);
                return await res.json();
            } catch (err) {
                if (retries > 0) {
                    await new Promise(r => setTimeout(r, backoff));
                    return fetchWithRetry(url, options, retries - 1, backoff * 1.5);
                }
                throw err;
            }
        };

        const loadBootstrapData = async () => {
            try {
                const data = await fetchWithRetry(`${API_BASE_URL}/bootstrap`);

                if (data.faculty) setFaculty(data.faculty);
                if (data.metadata) setMetadata(data.metadata);
                if (data.academic_plan) setAcademicPlan(data.academic_plan);
                if (data.views) setViews(data.views);
                if (data.official) {
                    setOfficialFiles({
                        timetable: data.official.timetable.exists ? data.official.timetable : null,
                        datesheet: data.official.datesheet.exists ? data.official.datesheet : null
                    });
                }
            } catch (err) {
                console.error("Bootstrap failed after retries:", err);
                setError("Unable to connect to service. Please refresh in a moment.");
            }
        };

        loadBootstrapData();
    }, []);

    const findFaculty = (teacherName) => {
        if (!teacherName) return null;

        // Aggressive normalization helper
        const normalize = (n) => n.toLowerCase()
            .replace(/^(dr|mr|ms|mrs|syed|s)\.?(\s+|$)/, '') // Remove common titles
            .replace(/[^a-z\s]/g, ' ') // Replace all non-alphabetic chars (like "5" in "El5lahi") with space
            .replace(/\s+/g, ' ')
            .trim();

        const lower = normalize(teacherName);
        if (!lower) return null;

        const nameParts = lower.split(/\s+/).filter(p => p.length >= 1);

        // 1. Try Exact Match (e.g., "hafsa" === "hafsa")
        let match = faculty.find(f => normalize(f.name) === lower);
        if (match) return match;

        // 2. Multi-word Match (handling initials and minor OCR errors)
        match = faculty.find(f => {
            const fn = normalize(f.name);
            const fnParts = fn.split(/\s+/);

            // At least 2 words must match (or 1 if it's the only word)
            let matchedCount = 0;
            nameParts.forEach(p => {
                const isPartMatch = p.length === 1
                    ? fnParts.some(fnp => fnp.startsWith(p))
                    : fnParts.some(fnp => fnp === p) || fn.includes(p);
                if (isPartMatch) matchedCount++;
            });

            // True if all parts matched, OR at least 2 parts match and it's > 70% of the input
            if (matchedCount === nameParts.length) return true;
            if (matchedCount >= 2 && matchedCount / nameParts.length >= 0.7) return true;
            return false;
        });
        if (match) return match;

        // 3. Last Resort: Substring (if name is long/unique enough)
        if (lower.length > 4) {
            match = faculty.find(f => normalize(f.name).includes(lower));
            if (match) return match;
        }

        // 4. Fallback to placeholder if teacher is known in metadata
        const isKnown = metadata.teachers.some(t => normalize(t) === lower);
        return {
            name: teacherName,
            designation: isKnown ? "Faculty" : "Instructor",
            department: "University Faculty",
            email: "",
            phone: "",
            photo_url: "",
            isPlaceholder: true
        };
    };
    const handleDrop = useCallback((e, type) => {
        e.preventDefault();
        setDragOver(prev => ({ ...prev, [type]: false }));
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            if (type === 'timetable') setTimetableFile(file);
            if (type === 'datesheet') setDatesheetFile(file);
        }
    }, []);

    const handleDragOver = useCallback((e, type) => {
        e.preventDefault();
        setDragOver(prev => ({ ...prev, [type]: true }));
    }, []);

    const handleDragLeave = useCallback((e, type) => {
        e.preventDefault();
        setDragOver(prev => ({ ...prev, [type]: false }));
    }, []);

    const handleFileChange = (e, type) => {
        const file = e.target.files[0];
        if (type === 'timetable') setTimetableFile(file);
        if (type === 'datesheet') setDatesheetFile(file);
    };

    const handleExtract = async () => {
        if (!rollNumber) { setError('Please enter a Roll Number.'); return; }

        const needTimetable = !useOfficial.timetable || !officialFiles.timetable;
        if (needTimetable && !timetableFile) { setError('Please upload the Timetable PDF or use the official one.'); return; }

        const needDatesheet = includeExams && (!useOfficial.datesheet || !officialFiles.datesheet);
        if (needDatesheet && !datesheetFile) { setError('Please upload the Datesheet PDF or use the official one.'); return; }

        setLoading(true);
        setError('');
        setSchedule(null);

        const formData = new FormData();
        formData.append('roll_number', rollNumber);
        if (timetableFile && !useOfficial.timetable) {
            formData.append('timetable_file', timetableFile);
        }
        if (includeExams && datesheetFile && !useOfficial.datesheet) {
            formData.append('datesheet_file', datesheetFile);
        }

        try {
            const res = await fetch(`${API_BASE_URL}/parse`, { method: 'POST', body: formData });
            if (!res.ok) {
                const errorText = await res.text();
                let errorMsg = res.statusText;
                try { const ej = JSON.parse(errorText); if (ej.detail) errorMsg = ej.detail; } catch { }
                throw new Error(`Failed to parse schedule: ${errorMsg}`);
            }
            const data = await res.json();
            setSchedule(data);
            // Cache the result
            localStorage.setItem('timetable_cache', JSON.stringify(data));
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const performSync = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(schedule),
            });
            if (res.status === 401) { setSyncStatus('auth_needed'); return; }
            const data = await res.json();
            if (res.ok) setSyncStatus('success');
            else setSyncStatus(`error:${data.detail}`);
        } catch (err) {
            setSyncStatus(`error:${err.message}`);
        }
    };

    const handleSync = async () => {
        if (!schedule) return;
        setSyncStatus('syncing');
        try {
            const authRes = await fetch(`${API_BASE_URL}/auth/url`);
            if (!authRes.ok) throw new Error("Failed to check auth status");
            const authData = await authRes.json();
            if (authData.error) throw new Error(authData.error);
            if (!authData.authenticated && authData.url) {
                const w = 500, h = 600;
                const left = (window.innerWidth - w) / 2, top = (window.innerHeight - h) / 2;
                const popup = window.open(authData.url, 'Google Auth', `width=${w},height=${h},top=${top},left=${left}`);
                if (!popup) { setSyncStatus('popup_blocked'); return; }
                const timer = setInterval(async () => {
                    if (popup.closed) {
                        clearInterval(timer);
                        const checkRes = await fetch(`${API_BASE_URL}/auth/url`);
                        const checkData = await checkRes.json();
                        if (checkData.authenticated) { setSyncStatus('syncing'); await performSync(); }
                        else setSyncStatus('auth_failed');
                    }
                }, 1000);
                return;
            }
            await performSync();
        } catch (err) {
            setSyncStatus(`error:${err.message}`);
        }
    };

    const handleDownloadICS = async () => {
        if (!schedule) return;
        try {
            const res = await fetch(`${API_BASE_URL}/download-ics`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(schedule),
            });
            if (res.ok) {
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `schedule_${rollNumber}.ics`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            }
        } catch (err) {
            console.error(err);
        }
    };

    const getSyncStatusDisplay = () => {
        if (!syncStatus) return null;
        const map = {
            syncing: { text: 'Syncing...', cls: 'status-info', icon: '⟳' },
            success: { text: 'Successfully synced!', cls: 'status-success', icon: '✓' },
            auth_needed: { text: 'Please authenticate first.', cls: 'status-warning', icon: '⚠' },
            auth_failed: { text: 'Auth failed or cancelled.', cls: 'status-error', icon: '✗' },
            popup_blocked: { text: 'Popup blocked! Allow popups.', cls: 'status-warning', icon: '⚠' },
        };
        if (map[syncStatus]) {
            const s = map[syncStatus];
            return <span className={`status-badge ${s.cls}`}><span className="status-icon">{s.icon}</span> {s.text}</span>;
        }
        if (syncStatus.startsWith('error:'))
            return <span className="status-badge status-error"><span className="status-icon">✗</span> {syncStatus.slice(6)}</span>;
        return null;
    };

    const FileDropZone = ({ type, file, fileRef, label, icon }) => (
        <div
            className={`drop-zone ${dragOver[type] ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}
            onDrop={(e) => handleDrop(e, type)}
            onDragOver={(e) => handleDragOver(e, type)}
            onDragLeave={(e) => handleDragLeave(e, type)}
            onClick={() => fileRef.current?.click()}
        >
            <input ref={fileRef} type="file" accept=".pdf" onChange={(e) => handleFileChange(e, type)} style={{ display: 'none' }} />
            <div className="drop-zone-icon">{icon}</div>
            <div className="drop-zone-text">
                {file ? (
                    <>
                        <span className="file-name">{file.name}</span>
                        <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                    </>
                ) : (
                    <>
                        <span className="drop-label">{label}</span>
                        <span className="drop-hint">Drag & drop or click to browse</span>
                    </>
                )}
            </div>
        </div>
    );



    const dayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    return (
        <div className="app">
            <Head>
                <title>Easy Timetable</title>
                <meta name="description" content="Upload your university PDFs to generate a personalized class & exam schedule." />
            </Head>

            <div className="bg-orb bg-orb-1" />
            <div className="bg-orb bg-orb-2" />

            <header className="header">
                <div className="logo">
                    <span className="logo-icon">📅</span>
                    <span className="logo-text">Easy <span className="logo-accent">Timetable</span></span>
                    {views !== null && (
                        <div className="view-counter">
                            <span className="view-dot"></span>
                            {views.toLocaleString()} views
                        </div>
                    )}
                </div>
            </header>

            <main className="main">
                <section className="hero">
                    <h1 className="hero-title">
                        Your Schedule,<br />
                        <span className="hero-gradient">Organized Instantly</span>
                    </h1>
                    <p className="hero-subtitle">
                        Upload your university timetable PDF to extract, view, and sync your personalized schedule.
                    </p>
                </section>

                <section className="upload-section">
                    <div className="glass-card">
                        <h2 className="section-title">
                            <span className="section-icon">🎓</span>
                            Get Started
                        </h2>

                        <div className="input-wrapper">
                            <label className="input-label">Roll Number</label>
                            <div className="text-input-container">
                                <span className="input-icon">🆔</span>
                                <input
                                    id="roll-number-input"
                                    type="text"
                                    className="text-input"
                                    value={rollNumber}
                                    onChange={(e) => setRollNumber(e.target.value)}
                                    placeholder="e.g. 24P-0529"
                                />
                            </div>
                        </div>

                        <div className="file-grid single">
                            {officialFiles.timetable ? (
                                <div className="official-status-card">
                                    <div className="official-info">
                                        <span className="official-icon">✅</span>
                                        <div className="official-text">
                                            <div className="official-label">Official Timetable detected</div>
                                            <div className="official-sub">Spring 2026 Season</div>
                                        </div>
                                    </div>
                                    <label className="toggle-container mini">
                                        <input
                                            type="checkbox"
                                            checked={useOfficial.timetable}
                                            onChange={(e) => setUseOfficial(prev => ({ ...prev, timetable: e.target.checked }))}
                                            className="toggle-input"
                                        />
                                        <span className="toggle-slider" />
                                        <span className="toggle-label">Use Default</span>
                                    </label>
                                </div>
                            ) : null}

                            {(!officialFiles.timetable || !useOfficial.timetable) && (
                                <FileDropZone
                                    type="timetable"
                                    file={timetableFile}
                                    fileRef={timetableRef}
                                    label="Student Timetable PDF"
                                    icon="📄"
                                />
                            )}
                        </div>

                        {/* Optional exams toggle */}
                        <div className="toggle-row">
                            <label className="toggle-container" htmlFor="include-exams">
                                <input
                                    id="include-exams"
                                    type="checkbox"
                                    checked={includeExams}
                                    onChange={(e) => setIncludeExams(e.target.checked)}
                                    className="toggle-input"
                                />
                                <span className="toggle-slider" />
                                <span className="toggle-label">Include Exam Datesheet</span>
                            </label>
                        </div>

                        {includeExams && (
                            <div className="file-grid single fade-in">
                                {officialFiles.datesheet ? (
                                    <div className="official-status-card">
                                        <div className="official-info">
                                            <span className="official-icon">📝</span>
                                            <div className="official-text">
                                                <div className="official-label">Official Datesheet detected</div>
                                                <div className="official-sub">Tentative Sessional 1</div>
                                            </div>
                                        </div>
                                        <label className="toggle-container mini">
                                            <input
                                                type="checkbox"
                                                checked={useOfficial.datesheet}
                                                onChange={(e) => setUseOfficial(prev => ({ ...prev, datesheet: e.target.checked }))}
                                                className="toggle-input"
                                            />
                                            <span className="toggle-slider" />
                                            <span className="toggle-label">Use Default</span>
                                        </label>
                                    </div>
                                ) : null}

                                {(!officialFiles.datesheet || !useOfficial.datesheet) && (
                                    <FileDropZone
                                        type="datesheet"
                                        file={datesheetFile}
                                        fileRef={datesheetRef}
                                        label="Exam Datesheet PDF"
                                        icon="📝"
                                    />
                                )}
                            </div>
                        )}

                        <button id="extract-btn" className="btn btn-primary" onClick={handleExtract} disabled={loading}>
                            {loading ? (<><span className="spinner" /> Extracting...</>) : (<><span className="btn-icon">⚡</span> Extract Schedule</>)}
                        </button>

                        {error && (
                            <div className="error-banner">
                                <span className="error-icon">⚠</span>
                                {error}
                            </div>
                        )}
                    </div>
                </section>

                {schedule && (
                    <section className="results-section fade-in">
                        <div className="glass-card">
                            <div className="results-header">
                                <h2 className="section-title">
                                    <span className="section-icon">📊</span>
                                    Schedule for <span className="highlight">{schedule.roll_number}</span>
                                    <button
                                        className="btn-text-small"
                                        onClick={() => { localStorage.removeItem('timetable_cache'); setSchedule(null); }}
                                        title="Clear local cache and start over"
                                    >
                                        ✕ Clear
                                    </button>
                                </h2>
                                <div className="tab-bar">
                                    <button className={`tab-btn ${activeTab === 'classes' ? 'active' : ''}`} onClick={() => setActiveTab('classes')}>
                                        <span className="tab-icon">📚</span> Classes
                                        <span className="tab-count">{schedule.weekly_schedule.length}</span>
                                    </button>
                                    {includeExams && schedule.exam_schedule.length > 0 && (
                                        <button className={`tab-btn ${activeTab === 'exams' ? 'active' : ''}`} onClick={() => setActiveTab('exams')}>
                                            <span className="tab-icon">✏️</span> Exams
                                            <span className="tab-count">{schedule.exam_schedule.length}</span>
                                        </button>
                                    )}
                                    {academicPlan.length > 0 && (
                                        <button className={`tab-btn ${activeTab === 'academic' ? 'active' : ''}`} onClick={() => setActiveTab('academic')}>
                                            <span className="tab-icon">📅</span> Academic Plan
                                            <span className="tab-count">{academicPlan.length}</span>
                                        </button>
                                    )}
                                </div>
                            </div>

                            <div className="tab-content">
                                {activeTab === 'classes' && (
                                    <div className="schedule-grid">
                                        {schedule.weekly_schedule.length === 0 ? (
                                            <p className="empty-state">No classes found for this roll number.</p>
                                        ) : (
                                            dayOrder.filter(day => schedule.weekly_schedule.some(c => c.day === day)).map(day => (
                                                <div key={day} className="day-group">
                                                    <div className="day-header">
                                                        <span className="day-name">{day}</span>
                                                        <span className="day-count">
                                                            {schedule.weekly_schedule.filter(c => c.day === day).length} classes
                                                        </span>
                                                    </div>
                                                    <div className="class-cards">
                                                        {schedule.weekly_schedule
                                                            .filter(c => c.day === day)
                                                            .sort((a, b) => {
                                                                const getVal = (t) => {
                                                                    const [h, m] = t.split(':').map(Number);
                                                                    return (h < 8 ? h + 12 : h) * 60 + m;
                                                                };
                                                                return getVal(a.start_time) - getVal(b.start_time);
                                                            })
                                                            .map((cls, idx) => {
                                                                const fac = findFaculty(cls.teacher);
                                                                return (
                                                                    <div key={idx} className="class-card">
                                                                        <div className="class-time">
                                                                            <span className="time-dot" />
                                                                            {cls.start_time} – {cls.end_time}
                                                                        </div>
                                                                        <div className="class-info">
                                                                            <div className="class-subject">{cls.subject}</div>
                                                                            <div className="class-meta">
                                                                                <span className="meta-item">
                                                                                    <span className="meta-icon">📍</span> {cls.room || 'TBA'}
                                                                                </span>
                                                                                <button
                                                                                    className={`teacher-chip ${fac.isPlaceholder ? 'placeholder' : ''}`}
                                                                                    onClick={() => setSelectedTeacher(fac)}
                                                                                >
                                                                                    <img
                                                                                        src={fac.photo_local || fac.photo_url}
                                                                                        alt=""
                                                                                        className="teacher-chip-photo"
                                                                                        onError={(e) => {
                                                                                            const bgColor = fac.isPlaceholder ? '94a3b8' : '6366f1';
                                                                                            e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(fac.name)}&background=${bgColor}&color=fff&size=48`;
                                                                                        }}
                                                                                    />
                                                                                    <span className="teacher-chip-name">{cls.teacher}</span>
                                                                                </button>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}

                                {activeTab === 'exams' && includeExams && (
                                    <div className="schedule-grid">
                                        <div className="exam-type-header">
                                            <span className="exam-type-badge">{schedule.exam_type || 'Examination Schedule'}</span>
                                        </div>
                                        {schedule.exam_schedule.length === 0 ? (
                                            <p className="empty-state">No exams found.</p>
                                        ) : (
                                            // Group exams by date
                                            Object.entries(
                                                schedule.exam_schedule.reduce((groups, exam) => {
                                                    const date = exam.date;
                                                    if (!groups[date]) groups[date] = [];
                                                    groups[date].push(exam);
                                                    return groups;
                                                }, {})
                                            )
                                                .sort((a, b) => {
                                                    // Sort dates: "Sat, 21 Feb 2026"
                                                    const parseDate = (d) => {
                                                        try {
                                                            const p = d.split(', ');
                                                            if (p.length < 2) return 0;
                                                            const dateParts = p[1].split(' '); // ["21", "Feb", "2026"]
                                                            const day = parseInt(dateParts[0]);
                                                            const monthStr = dateParts[1];
                                                            const year = parseInt(dateParts[2]);
                                                            const months = { 'Jan': 0, 'Feb': 1, 'Mar': 2, 'Apr': 3, 'May': 4, 'Jun': 5, 'Jul': 6, 'Aug': 7, 'Sep': 8, 'Oct': 9, 'Nov': 10, 'Dec': 11 };
                                                            return new Date(year, months[monthStr], day).getTime();
                                                        } catch (e) { return 0; }
                                                    };
                                                    return parseDate(a[0]) - parseDate(b[0]);
                                                })
                                                .map(([date, dayExams]) => (
                                                    <div key={date} className="day-group">
                                                        <div className="day-header">
                                                            <span className="day-name">{date}</span>
                                                            <span className="day-count">
                                                                {dayExams.length} {dayExams.length === 1 ? 'exam' : 'exams'}
                                                            </span>
                                                        </div>
                                                        <div className="class-cards">
                                                            {dayExams.map((exam, idx) => (
                                                                <div className="class-card" key={idx}>
                                                                    <div className="class-time">
                                                                        <div className="time-dot" />
                                                                        {exam.start_time} – {exam.end_time}
                                                                    </div>
                                                                    <div className="class-info">
                                                                        <div className="class-subject">{exam.subject}</div>
                                                                        <div className="class-meta">
                                                                            <span className="meta-item">
                                                                                <span className="meta-icon">👤</span> {exam.room || 'Instructor TBA'}
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))
                                        )}
                                    </div>
                                )}
                                {activeTab === 'academic' && (
                                    <div className="acad-container">
                                        {/* Holidays Section */}
                                        {academicPlan.some(i => i.type === 'holiday') && (
                                            <div className="acad-section">
                                                <h3 className="acad-section-title">
                                                    <span className="acad-section-icon">🏖️</span> Public Holidays & Mid-Semester Breaks
                                                </h3>
                                                <div className="acad-grid">
                                                    {academicPlan.filter(i => i.type === 'holiday').map((item, idx) => (
                                                        <div key={idx} className={`acad-card ${item.type}`}>
                                                            <div className="acad-type-indicator" />
                                                            <div className="acad-date-side">
                                                                <div className="acad-week">Week {item.week}</div>
                                                                <div className="acad-day">{item.day}</div>
                                                            </div>
                                                            <div className="acad-main">
                                                                <div className="acad-date">{item.date}</div>
                                                                <div className="acad-desc">{item.description}</div>
                                                                <div className={`acad-badge ${item.type}`}>{item.type}</div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Exam & Timeline Section */}
                                        <div className="acad-section">
                                            <h3 className="acad-section-title">
                                                <span className="acad-section-icon">📅</span> Academic Journey & Milestones
                                            </h3>
                                            {/* Group by week */}
                                            {Object.entries(
                                                academicPlan
                                                    .filter(i => i.type !== 'holiday')
                                                    .reduce((groups, item) => {
                                                        const week = item.week;
                                                        if (!groups[week]) groups[week] = [];
                                                        groups[week].push(item);
                                                        return groups;
                                                    }, {})
                                            )
                                                .sort((a, b) => {
                                                    const getW = (w) => parseInt(w) || (w.includes('-') ? parseInt(w.split('-')[0]) : 99);
                                                    return getW(a[0]) - getW(b[0]);
                                                })
                                                .map(([week, weekItems]) => (
                                                    <div key={week} className="day-group">
                                                        <div className="day-header">
                                                            <span className="day-name">Week {week}</span>
                                                            <span className="day-count">{weekItems.length} items</span>
                                                        </div>
                                                        <div className="acad-grid">
                                                            {weekItems.map((item, idx) => (
                                                                <div key={idx} className={`acad-card ${item.type}`}>
                                                                    <div className="acad-type-indicator" />
                                                                    <div className="acad-main">
                                                                        <div className="acad-date">{item.date} ({item.day})</div>
                                                                        <div className="acad-desc">{item.description}</div>
                                                                        <div className={`acad-badge ${item.type}`}>{item.type}</div>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="actions-bar">
                            <button className="btn btn-success" onClick={handleSync}>
                                <span className="btn-icon">📅</span> Sync to Google Calendar
                            </button>
                            <button className="btn btn-outline" onClick={handleDownloadICS}>
                                <span className="btn-icon">⬇</span> Download .ICS
                            </button>
                        </div>

                        {getSyncStatusDisplay() && (
                            <div className="sync-status-bar">{getSyncStatusDisplay()}</div>
                        )}
                    </section>
                )}
            </main>

            {/* Teacher profile modal */}
            {selectedTeacher && (
                <div className="modal-overlay" onClick={() => setSelectedTeacher(null)}>
                    <div className="modal-card" onClick={e => e.stopPropagation()}>
                        <button className="modal-close" onClick={() => setSelectedTeacher(null)}>×</button>
                        <div className="modal-photo-wrapper">
                            <img
                                src={selectedTeacher.photo_local || selectedTeacher.photo_url}
                                alt={selectedTeacher.name}
                                className="modal-photo"
                                onError={(e) => { e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(selectedTeacher.name)}&background=6366f1&color=fff&size=200`; }}
                            />
                        </div>
                        <h3 className="modal-name">{selectedTeacher.name}</h3>
                        <p className="modal-designation">{selectedTeacher.designation}</p>
                        {selectedTeacher.department && <p className="modal-dept">{selectedTeacher.department}</p>}
                        <div className="modal-details">
                            {selectedTeacher.isPlaceholder ? (
                                <div className="modal-info-needed">
                                    <span className="modal-detail-icon">ℹ️</span>
                                    <span>Detailed profile information is not available for this instructor yet.</span>
                                </div>
                            ) : (
                                <>
                                    {selectedTeacher.email && (
                                        <a href={`mailto:${selectedTeacher.email}`} className="modal-detail-item modal-email">
                                            <span className="modal-detail-icon">📧</span>
                                            <span>{selectedTeacher.email}</span>
                                        </a>
                                    )}
                                    {selectedTeacher.phone && (
                                        <div className="modal-detail-item">
                                            <span className="modal-detail-icon">📞</span>
                                            <span>{selectedTeacher.phone}</span>
                                        </div>
                                    )}
                                    {selectedTeacher.profile_url && (
                                        <a href={selectedTeacher.profile_url} target="_blank" rel="noopener noreferrer" className="modal-detail-item modal-link">
                                            <span className="modal-detail-icon">🔗</span>
                                            <span>View Profile</span>
                                        </a>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <footer className="footer">
                <p>Easy Timetable — Built for students, by students. <span style={{ opacity: 0.8 }}>Vibe Coded by Hisam Mehboob.</span></p>
            </footer>

            <style jsx>{`
                .official-status-card {
                    display: flex; align-items: center; justify-content: space-between;
                    padding: 0.8rem 1rem; background: rgba(16, 185, 129, 0.08);
                    border: 1px solid rgba(16, 185, 129, 0.2); border-radius: var(--radius-md);
                    margin-bottom: 0.5rem; animation: slideDownInner 0.3s ease;
                }
                .official-info { display: flex; align-items: center; gap: 0.75rem; }
                .official-icon { font-size: 1.2rem; }
                .official-text { display: flex; flex-direction: column; }
                .official-label { font-size: 0.85rem; font-weight: 600; color: #10b981; }
                .official-sub { font-size: 0.75rem; color: var(--text-muted); }
                
                .acad-container { padding: 0.5rem; display: flex; flex-direction: column; gap: 2.5rem; }
                .acad-section { display: flex; flex-direction: column; gap: 1.25rem; }
                .acad-section-title { 
                    font-size: 1.1rem; font-weight: 700; color: var(--text-primary); 
                    display: flex; align-items: center; gap: 0.75rem; padding-bottom: 0.5rem;
                    border-bottom: 1px solid rgba(255,255,255,0.05);
                }
                .acad-section-icon { 
                    width: 32px; height: 32px; background: rgba(255,255,255,0.05); 
                    border-radius: 8px; display: flex; align-items: center; justify-content: center;
                    font-size: 1rem;
                }

                .acad-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
                .acad-card { 
                    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: var(--radius-lg); display: flex; overflow: hidden; position: relative;
                    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                }
                .acad-card:hover { transform: translateY(-3px); background: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.15); box-shadow: 0 10px 20px -10px rgba(0,0,0,0.5); }
                
                .acad-card.exam { 
                    background: rgba(168, 85, 247, 0.08); border-color: rgba(168, 85, 247, 0.3);
                    box-shadow: 0 0 15px -5px rgba(168, 85, 247, 0.2);
                }
                .acad-card.critical { 
                    background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.3);
                    box-shadow: 0 0 15px -5px rgba(239, 68, 68, 0.2);
                }

                .acad-type-indicator { width: 4px; height: 100%; position: absolute; left: 0; top: 0; }
                .acad-card.critical .acad-type-indicator { background: #ef4444; }
                .acad-card.exam .acad-type-indicator { background: #a855f7; }
                .acad-card.deadline .acad-type-indicator { background: #f59e0b; }
                .acad-card.holiday .acad-type-indicator { background: #10b981; }
                .acad-card.result .acad-type-indicator { background: #3b82f6; }
                .acad-card.event .acad-type-indicator { background: #64748b; }

                .acad-date-side { padding: 1rem; background: rgba(255, 255, 255, 0.02); display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 90px; border-right: 1px solid rgba(255, 255, 255, 0.05); }
                .acad-week { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
                .acad-day { font-size: 1.1rem; font-weight: 800; color: var(--text-primary); }
                
                .acad-main { padding: 1.25rem; flex: 1; display: flex; flex-direction: column; gap: 0.35rem; }
                .acad-date { font-size: 0.85rem; font-weight: 600; color: var(--accent-primary); }
                .acad-desc { font-size: 1rem; font-weight: 500; color: var(--text-primary); line-height: 1.4; }
                .acad-badge { 
                    align-self: flex-start; margin-top: 0.6rem; padding: 0.2rem 0.6rem; border-radius: 999px; 
                    font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
                }
                .acad-badge.critical { background: rgba(239, 68, 68, 0.15); color: #f87171; }
                .acad-badge.exam { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
                .acad-badge.deadline { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
                .acad-badge.holiday { background: rgba(16, 185, 129, 0.15); color: #34d399; }
                .acad-badge.result { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
                .acad-badge.event { background: rgba(100, 116, 139, 0.15); color: #94a3b8; }

                .toggle-container.mini { margin: 0; padding: 0.25rem 0.6rem; background: rgba(255,255,255,0.03); border-radius: 999px; }
                .toggle-container.mini .toggle-label { font-size: 0.7rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; }

                .exam-type-header { margin-bottom: 1.5rem; display: flex; justify-content: center; }
                .exam-type-badge { 
                    padding: 0.4rem 1.25rem; background: rgba(168, 85, 247, 0.1); 
                    border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 999px;
                    color: #c084fc; font-size: 0.9rem; font-weight: 700; text-transform: uppercase;
                    letter-spacing: 0.05em; box-shadow: 0 0 15px -5px rgba(168, 85, 247, 0.3);
                }

                .view-counter {
                    margin-left: 1rem; padding: 0.25rem 0.75rem; background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 999px;
                    font-size: 0.75rem; font-weight: 600; color: var(--text-secondary);
                    display: flex; align-items: center; gap: 0.5rem;
                }
                .view-dot { width: 6px; height: 6px; background: #10b981; border-radius: 50%; box-shadow: 0 0 8px #10b981; }

                @keyframes slideDownInner {
                    from { opacity: 0; transform: translateY(-10px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .app {
                    min-height: 100vh;
                    position: relative;
                    overflow: hidden;
                }
                .bg-orb {
                    position: fixed;
                    border-radius: 50%;
                    filter: blur(100px);
                    opacity: 0.15;
                    pointer-events: none;
                    z-index: 0;
                }
                .bg-orb-1 { width: 600px; height: 600px; background: var(--accent-primary); top: -200px; right: -200px; }
                .bg-orb-2 { width: 500px; height: 500px; background: var(--accent-secondary); bottom: -150px; left: -150px; }

                .header {
                    position: sticky; top: 0; z-index: 100;
                    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                    background: rgba(10, 10, 18, 0.8);
                    border-bottom: 1px solid var(--border-subtle);
                    padding: 1rem 2rem;
                }
                .logo { display: flex; align-items: center; gap: 0.75rem; max-width: 1000px; margin: 0 auto; }
                .logo-icon { font-size: 1.5rem; }
                .logo-text { font-size: 1.2rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
                .logo-accent { background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }

                .main { position: relative; z-index: 1; max-width: 1000px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }

                .hero { text-align: center; padding: 3rem 0 2.5rem; }
                .hero-title { font-size: 3rem; font-weight: 800; line-height: 1.1; letter-spacing: -0.03em; color: var(--text-primary); margin-bottom: 1rem; }
                .hero-gradient { background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
                .hero-subtitle { font-size: 1.1rem; color: var(--text-secondary); max-width: 540px; margin: 0 auto; line-height: 1.6; }

                .glass-card {
                    background: var(--bg-card); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
                    border: 1px solid var(--border-subtle); border-radius: var(--radius-xl);
                    padding: 2rem; margin-bottom: 1.5rem; transition: border-color 0.3s;
                }
                .glass-card:hover { border-color: var(--border-glow); }

                .section-title { display: flex; align-items: center; gap: 0.6rem; font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin-bottom: 1.5rem; }
                .section-icon { font-size: 1.2rem; }
                .highlight { color: var(--accent-primary); font-family: 'Inter', monospace; }

                .input-wrapper { margin-bottom: 1.5rem; }
                .input-label { display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
                .text-input-container {
                    display: flex; align-items: center; gap: 0.75rem;
                    background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
                    padding: 0 1rem; transition: border-color 0.2s, box-shadow 0.2s;
                }
                .text-input-container:focus-within { border-color: var(--accent-primary); box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
                .input-icon { font-size: 1.1rem; opacity: 0.6; }
                .text-input { flex: 1; background: transparent; border: none; outline: none; padding: 0.9rem 0; font-size: 1rem; font-family: 'Inter', sans-serif; color: var(--text-primary); }
                .text-input::placeholder { color: var(--text-muted); }

                .file-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
                .file-grid.single { grid-template-columns: 1fr; }
                .drop-zone {
                    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.75rem;
                    padding: 2rem 1rem; border: 2px dashed var(--border-subtle); border-radius: var(--radius-lg);
                    background: rgba(255,255,255,0.01); cursor: pointer; transition: all 0.3s ease;
                    text-align: center; min-height: 120px;
                }
                .drop-zone:hover { border-color: var(--accent-primary); background: rgba(99,102,241,0.04); }
                .drop-zone.drag-active { border-color: var(--accent-primary); background: rgba(99,102,241,0.08); box-shadow: var(--shadow-glow); transform: scale(1.02); }
                .drop-zone.has-file { border-color: var(--accent-success); border-style: solid; background: rgba(16,185,129,0.04); }
                .drop-zone-icon { font-size: 2rem; }
                .drop-zone-text { display: flex; flex-direction: column; gap: 0.25rem; }
                .drop-label { font-weight: 600; font-size: 0.95rem; color: var(--text-primary); }
                .drop-hint { font-size: 0.8rem; color: var(--text-muted); }
                .file-name { font-weight: 600; color: var(--accent-success); font-size: 0.9rem; word-break: break-all; }
                .file-size { font-size: 0.75rem; color: var(--text-muted); }

                /* Toggle */
                .toggle-row { margin-bottom: 1.5rem; }
                .toggle-container { display: flex; align-items: center; gap: 0.75rem; cursor: pointer; user-select: none; }
                .toggle-input { display: none; }
                .toggle-slider {
                    position: relative; width: 44px; height: 24px;
                    background: rgba(255,255,255,0.1); border-radius: 12px;
                    transition: background 0.3s; flex-shrink: 0;
                }
                .toggle-slider::after {
                    content: ''; position: absolute; top: 3px; left: 3px;
                    width: 18px; height: 18px; border-radius: 50%;
                    background: var(--text-muted); transition: all 0.3s;
                }
                .toggle-input:checked + .toggle-slider { background: var(--accent-primary); }
                .toggle-input:checked + .toggle-slider::after { left: 23px; background: white; }
                .toggle-label { font-size: 0.9rem; color: var(--text-secondary); font-weight: 500; }

                /* Buttons */
                .btn {
                    display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
                    padding: 0.85rem 1.8rem; border: none; border-radius: var(--radius-md);
                    font-size: 1rem; font-weight: 600; font-family: 'Inter', sans-serif;
                    cursor: pointer; transition: all 0.25s ease; position: relative; overflow: hidden;
                }
                .btn:disabled { opacity: 0.5; cursor: not-allowed; }
                .btn-icon { font-size: 1.1rem; }
                .btn-primary { width: 100%; background: var(--gradient-primary); color: white; box-shadow: 0 4px 15px rgba(99,102,241,0.3); }
                .btn-primary:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 6px 25px rgba(99,102,241,0.4); }
                .btn-success { background: var(--gradient-success); color: white; box-shadow: 0 4px 15px rgba(16,185,129,0.3); }
                .btn-success:hover { transform: translateY(-2px); box-shadow: 0 6px 25px rgba(16,185,129,0.4); }
                .btn-outline { background: transparent; color: var(--text-primary); border: 1px solid var(--border-subtle); }
                .btn-outline:hover { background: rgba(255,255,255,0.05); border-color: var(--text-muted); transform: translateY(-2px); }
                .spinner { width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3); border-top-color: white; border-radius: 50%; animation: spin 0.6s linear infinite; }

                .error-banner { display: flex; align-items: center; gap: 0.6rem; margin-top: 1rem; padding: 0.85rem 1rem; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-md); color: #fca5a5; font-size: 0.9rem; }

                .results-section { margin-top: 1rem; }
                .fade-in { animation: fadeInUp 0.5s ease forwards; }
                .results-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.5rem; }
                .results-header .section-title { margin-bottom: 0; }

                .tab-bar { display: flex; gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: var(--radius-md); padding: 4px; }
                .tab-btn {
                    display: flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1rem;
                    border: none; border-radius: var(--radius-sm); background: transparent;
                    color: var(--text-muted); font-size: 0.85rem; font-weight: 600; font-family: 'Inter', sans-serif;
                    cursor: pointer; transition: all 0.2s;
                }
                .tab-btn:hover { color: var(--text-secondary); }
                .tab-btn.active { background: var(--accent-primary); color: white; }
                .tab-count { background: rgba(255,255,255,0.15); padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.7rem; font-weight: 700; }

                .schedule-grid { display: flex; flex-direction: column; gap: 1.5rem; }
                .day-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border-subtle); }
                .day-name { font-size: 1rem; font-weight: 700; color: var(--accent-primary); letter-spacing: 0.02em; }
                .day-count { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

                .class-cards { display: flex; flex-direction: column; gap: 0.6rem; }
                .class-card {
                    display: flex; gap: 1rem; padding: 0.9rem 1rem;
                    background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle);
                    border-radius: var(--radius-md); transition: all 0.2s;
                }
                .class-card:hover { background: rgba(255,255,255,0.04); border-color: var(--border-glow); transform: translateX(4px); }
                .class-time { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; font-weight: 600; color: var(--accent-secondary); white-space: nowrap; min-width: 120px; }
                .time-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-primary); flex-shrink: 0; }
                .class-info { flex: 1; min-width: 0; }
                .class-subject { font-weight: 600; font-size: 0.95rem; color: var(--text-primary); margin-bottom: 0.3rem; }
                .class-meta { display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }
                .meta-item { display: flex; align-items: center; gap: 0.3rem; font-size: 0.8rem; color: var(--text-muted); }
                .meta-icon { font-size: 0.85rem; }

                /* Teacher chip */
                .teacher-chip {
                    display: inline-flex; align-items: center; gap: 0.4rem;
                    padding: 0.2rem 0.6rem 0.2rem 0.2rem;
                    background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.15);
                    border-radius: 999px; cursor: pointer; font-family: 'Inter', sans-serif;
                    transition: all 0.2s; font-size: 0.8rem; color: #a5b4fc;
                }
                .teacher-chip:hover { background: rgba(99,102,241,0.15); border-color: rgba(99,102,241,0.3); transform: scale(1.03); }
                .teacher-chip-photo {
                    width: 22px; height: 22px; border-radius: 50%; object-fit: cover;
                    border: 1.5px solid rgba(99,102,241,0.3);
                }
                .teacher-chip-name { font-weight: 500; }

                /* Modal */
                .modal-overlay {
                    position: fixed; inset: 0; z-index: 1000;
                    background: rgba(0,0,0,0.6); backdrop-filter: blur(8px);
                    display: flex; align-items: center; justify-content: center;
                    padding: 1rem; animation: fadeInUp 0.25s ease forwards;
                }
                .modal-card {
                    background: var(--bg-secondary); border: 1px solid var(--border-subtle);
                    border-radius: var(--radius-xl); padding: 2rem;
                    max-width: 380px; width: 100%; text-align: center; position: relative;
                    box-shadow: 0 25px 50px rgba(0,0,0,0.5);
                }
                .modal-close {
                    position: absolute; top: 1rem; right: 1rem;
                    background: rgba(255,255,255,0.05); border: 1px solid var(--border-subtle);
                    color: var(--text-muted); width: 32px; height: 32px;
                    border-radius: 50%; font-size: 1.2rem; cursor: pointer;
                    display: flex; align-items: center; justify-content: center;
                    transition: all 0.2s; font-family: 'Inter', sans-serif;
                }
                .modal-close:hover { background: rgba(255,255,255,0.1); color: var(--text-primary); }
                .modal-photo-wrapper { margin-bottom: 1rem; }
                .modal-photo {
                    width: 100px; height: 100px; border-radius: 50%; object-fit: cover;
                    border: 3px solid var(--accent-primary);
                    box-shadow: 0 0 20px rgba(99,102,241,0.2);
                }
                .modal-name { font-size: 1.2rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.25rem; }
                .modal-designation { font-size: 0.85rem; color: var(--accent-secondary); margin-bottom: 0.15rem; }
                .modal-dept { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem; }
                .modal-details { display: flex; flex-direction: column; gap: 0.5rem; }
                .modal-detail-item {
                    display: flex; align-items: center; gap: 0.5rem;
                    padding: 0.6rem 0.8rem;
                    background: rgba(255,255,255,0.03); border: 1px solid var(--border-subtle);
                    border-radius: var(--radius-sm); font-size: 0.85rem; color: var(--text-secondary);
                    text-decoration: none; transition: all 0.2s;
                }
                .modal-detail-item:hover { background: rgba(255,255,255,0.06); }
                .modal-detail-icon { font-size: 1rem; flex-shrink: 0; }
                .modal-email { color: #a5b4fc; }
                .modal-email:hover { color: white; background: rgba(99,102,241,0.1); }
                .modal-link { color: #6ee7b7; }
                .modal-link:hover { color: white; background: rgba(16,185,129,0.1); }

                /* Exam cards */
                .exams-list { display: flex; flex-direction: column; gap: 0.6rem; }
                .exam-card {
                    display: flex; gap: 1rem; align-items: center; padding: 1rem;
                    background: rgba(239,68,68,0.03); border: 1px solid rgba(239,68,68,0.1);
                    border-radius: var(--radius-md); transition: all 0.2s;
                }
                .exam-card:hover { background: rgba(239,68,68,0.06); border-color: rgba(239,68,68,0.2); transform: translateX(4px); }
                .exam-date-badge { display: flex; flex-direction: column; align-items: center; gap: 0.2rem; min-width: 110px; padding: 0.5rem 0.75rem; background: rgba(239,68,68,0.08); border-radius: var(--radius-sm); }
                .exam-day { font-size: 0.8rem; font-weight: 700; color: #fca5a5; }
                .exam-time { font-size: 0.75rem; color: var(--text-muted); }
                .exam-subject { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); line-height: 1.4; }

                .actions-bar { display: flex; gap: 1rem; margin-bottom: 1rem; }

                .sync-status-bar { margin-bottom: 1rem; }
                .status-badge { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1rem; border-radius: var(--radius-md); font-size: 0.85rem; font-weight: 500; }
                .status-info { background: rgba(99,102,241,0.1); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.2); }
                .status-success { background: rgba(16,185,129,0.1); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.2); }
                .status-warning { background: rgba(245,158,11,0.1); color: #fcd34d; border: 1px solid rgba(245,158,11,0.2); }
                .status-error { background: rgba(239,68,68,0.1); color: #fca5a5; border: 1px solid rgba(239,68,68,0.2); }

                .btn-text-small {
                    background: transparent; border: 1px solid var(--border-subtle);
                    color: var(--text-muted); font-size: 0.7rem; padding: 0.2rem 0.5rem;
                    border-radius: var(--radius-sm); cursor: pointer; margin-left: 1rem;
                    transition: all 0.2s; vertical-align: middle;
                }
                .btn-text-small:hover { border-color: var(--accent-error); color: var(--accent-error); background: rgba(239,68,68,0.05); }

                .empty-state { text-align: center; color: var(--text-muted); padding: 3rem 1rem; font-size: 0.95rem; }

                .footer { position: relative; z-index: 1; text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.8rem; border-top: 1px solid var(--border-subtle); }

                @media (max-width: 640px) {
                    .hero-title { font-size: 2rem; }
                    .glass-card { padding: 1.25rem; }
                    .file-grid { grid-template-columns: 1fr; }
                    .results-header { flex-direction: column; }
                    .class-card { flex-direction: column; gap: 0.5rem; }
                    .class-time { min-width: auto; }
                    .actions-bar { flex-direction: column; }
                    .btn { width: 100%; }
                    .exam-card { flex-direction: column; align-items: flex-start; }
                }
            `}</style>
        </div>
    );
}
