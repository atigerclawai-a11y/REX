/**
 * REX v2 — Arctic Intelligence UI
 * Fully responsive: desktop sidebar + mobile hamburger, iOS keyboard-safe input.
 */
import { useState, useEffect, useRef, useCallback, createContext, useContext } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Dynamic — works from any IP (iPhone, Mac, etc.)
const API    = window.location.origin
const WS_URL = window.location.origin.replace(/^http/, 'ws') + '/ws/chat'

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  blue:        '#0066FF',
  blueDark:    '#0052CC',
  blueLight:   '#EBF2FF',
  blueMid:     '#CCE0FF',
  secure:      '#1045B8',
  secureLight: '#E6EDFC',
  text:        '#0D1117',
  textMid:     '#4A5568',
  textMuted:   '#8B949E',
  border:      '#DDE1E9',
  bg:          '#F5F6F8',
  white:       '#FFFFFF',
  bgSecondary: '#F0F2F5',
  success:     '#1A7F37',
  error:       '#CF222E',
  // Rexxie palette — warm rose
  rexxie:      '#9B4F72',
  rexxieDark:  '#7A3A58',
  rexxieLight: '#FDEEF5',
  rexxieMid:   '#F2CEDF',
  rexxieBg:    '#FDF6F9',
}

// ── Appearance / Theming ───────────────────────────────────────────────────────
const DEFAULT_APPEARANCE = {
  fontSize: 14, theme: 'light', density: 'comfortable', accentColor: 'blue',
  customColors: { bg: '#F5F6F8', white: '#FFFFFF', accent: '#0066FF', text: '#0D1117' }
}

const DARK_TOKENS = {
  bg:'#0D1117', white:'#161B22', bgSecondary:'#21262D',
  text:'#E6EDF3', textMid:'#8B949E', textMuted:'#6E7681',
  border:'#30363D', blueLight:'#1C2A3E', blueMid:'#1C3A5E',
  rexxieLight:'#2D1B27', rexxieMid:'#4A2B3C', rexxieBg:'#1E1419',
}

const ACCENT_COLORS = {
  blue:  { blue:'#0066FF', blueDark:'#0052CC', blueLight:'#EBF2FF', blueMid:'#CCE0FF', secure:'#1045B8', secureLight:'#E6EDFC' },
  gold:  { blue:'#c9a84c', blueDark:'#a87828', blueLight:'#FFF8E0', blueMid:'#FFE9A0', secure:'#8a6020', secureLight:'#FFF5D0' },
  green: { blue:'#1A7F37', blueDark:'#156C2E', blueLight:'#E6F4EA', blueMid:'#AADDB8', secure:'#0F5528', secureLight:'#D6F0DD' },
}

function loadAppearance() {
  try { const s = localStorage.getItem('rex-appearance'); return s ? { ...DEFAULT_APPEARANCE, ...JSON.parse(s) } : DEFAULT_APPEARANCE }
  catch { return DEFAULT_APPEARANCE }
}
function saveAppearance(a) {
  try { localStorage.setItem('rex-appearance', JSON.stringify(a)) } catch {}
}

const ThemeCtx = createContext(C)
function useTheme() { return useContext(ThemeCtx) }

const DENSITY_PAD = { compact:'8px 11px', comfortable:'11px 14px', spacious:'14px 18px' }

const fmt = iso => iso ? new Date(iso).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''

const PROVIDER_META = {
  anthropic:  { label: 'Claude',      color: '#CC5500', icon: '⚡' },
  openai:     { label: 'ChatGPT',     color: '#10A37F', icon: '●' },
  google:     { label: 'Gemini',      color: '#4285F4', icon: '◆' },
  xai:        { label: 'Grok',        color: '#7B2FBE', icon: '✴' },
  perplexity: { label: 'Perplexity',  color: '#20808D', icon: '🔍' },
  librechat:  { label: 'LibreChat',   color: '#E85D26', icon: '🔗' },
  ollama:     { label: 'Local',       color: '#1A7F37', icon: '⬡' },
}

// ── Mobile detection (reactive) ────────────────────────────────────────────────
function useIsMobile() {
  const [mobile, setMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return mobile
}

// ── Gold Dino Egg ─────────────────────────────────────────────────────────────
// phase 0 = whole egg | phase 1 = hammer strikes + cracks | phase 2 = hatched
function GoldEgg({ phase = 0, size = 72 }) {
  const cracked = phase >= 1
  const hatched  = phase >= 2

  // viewBox is 100 × 122, egg sits in 0 0 100 122
  // Extra paddingTop gives room for the hammer above the egg
  const padTop = size * 0.45
  const w = size
  const h = size * 1.22 + padTop

  return (
    <div style={{
      position: 'relative',
      width:  w,
      height: h,
      display: 'flex',
      alignItems: 'flex-end',
      justifyContent: 'center',
      overflow: 'visible',
    }}>

      {/* ── Hammer ─────────────────────────────────────────── */}
      {!hatched && (
        <div style={{
          position:      'absolute',
          bottom:        size * 1.22 - size * 0.08,
          left:          '50%',
          // Handle pivot is bottom-right of the hammer emoji
          transformOrigin: '80% 90%',
          transform: cracked
            ? 'translateX(-30%) rotate(42deg)'
            : 'translateX(5%)  rotate(-52deg)',
          transition: cracked
            ? 'transform 0.13s cubic-bezier(0.4,2.2,0.5,1)'   // vicious fast swing
            : 'transform 0.35s cubic-bezier(0.4,0,0.2,1)',     // slow raise
          fontSize:    size * 0.55 + 'px',
          lineHeight:  1,
          pointerEvents: 'none',
          filter: 'drop-shadow(2px 3px 4px rgba(0,0,0,0.35))',
          zIndex: 10,
          userSelect: 'none',
        }}>🔨</div>
      )}

      {/* ── Egg SVG ────────────────────────────────────────── */}
      <svg
        width={w} height={size * 1.22}
        viewBox="0 0 100 122"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          overflow: 'visible',
          filter: cracked
            ? 'drop-shadow(0 6px 22px rgba(255,160,0,0.75))'
            : 'drop-shadow(0 3px 14px rgba(160,110,0,0.45))',
          transition: 'filter 0.3s, opacity 0.4s, transform 0.4s',
          opacity:   hatched ? 0 : 1,
          transform: hatched ? 'scale(1.28) translateY(-10px)' : 'scale(1)',
        }}
      >
        <defs>
          {/* ── Deep gold base gradient ── */}
          <radialGradient id="dEggBody" cx="36%" cy="28%" r="72%">
            <stop offset="0%"   stopColor="#FFF8C0" />
            <stop offset="18%"  stopColor="#F5C830" />
            <stop offset="50%"  stopColor="#C08A00" />
            <stop offset="78%"  stopColor="#8A5C00" />
            <stop offset="100%" stopColor="#5A3600" />
          </radialGradient>

          {/* ── Top cap gradient (slightly lighter) ── */}
          <radialGradient id="dEggCap" cx="40%" cy="35%" r="65%">
            <stop offset="0%"   stopColor="#FFEFAA" />
            <stop offset="40%"  stopColor="#E8B400" />
            <stop offset="100%" stopColor="#9A6A00" />
          </radialGradient>

          {/* ── Organic bumpy surface texture ── */}
          <filter id="dEggTex" x="-2%" y="-2%" width="104%" height="104%">
            <feTurbulence type="fractalNoise" baseFrequency="0.55 0.45"
              numOctaves="4" seed="42" result="noise" />
            <feColorMatrix type="saturate" values="0" in="noise" result="gray" />
            <feBlend in="SourceGraphic" in2="gray" mode="multiply" result="blend" />
            <feComposite in="blend" in2="SourceGraphic" operator="in" />
          </filter>

          {/* ── Orange crack-glow filter ── */}
          <filter id="dCrackGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feFlood floodColor="#FF8800" floodOpacity="0.85" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* ── Clip path = egg outline ── */}
          <clipPath id="dEggClip">
            <path d="M50 6 C22 6 5 36 5 66 C5 96 25 118 50 118 C75 118 95 96 95 66 C95 36 78 6 50 6 Z" />
          </clipPath>
        </defs>

        {/* ── BODY (whole egg silhouette) ── */}
        <path d="M50 6 C22 6 5 36 5 66 C5 96 25 118 50 118 C75 118 95 96 95 66 C95 36 78 6 50 6 Z"
          fill="url(#dEggBody)" />

        {/* ── Surface texture overlay ── */}
        <path d="M50 6 C22 6 5 36 5 66 C5 96 25 118 50 118 C75 118 95 96 95 66 C95 36 78 6 50 6 Z"
          fill="url(#dEggBody)" filter="url(#dEggTex)" opacity="0.55" />

        {/* ── Dino-egg mottling spots ── */}
        <g clipPath="url(#dEggClip)" opacity="0.42">
          <ellipse cx="38" cy="52" rx="6"   ry="4"   fill="#6B4000" transform="rotate(-18 38 52)" />
          <ellipse cx="64" cy="68" rx="5"   ry="3.5" fill="#5A3200" transform="rotate(12 64 68)" />
          <ellipse cx="44" cy="88" rx="7"   ry="4"   fill="#7A4800" transform="rotate(-8 44 88)" />
          <ellipse cx="70" cy="45" rx="4"   ry="2.8" fill="#6B4000" transform="rotate(22 70 45)" />
          <ellipse cx="26" cy="76" rx="4.5" ry="3"   fill="#5A3200" transform="rotate(-12 26 76)" />
          <ellipse cx="58" cy="100" rx="5"  ry="3"   fill="#6B4000" transform="rotate(6 58 100)" />
          <ellipse cx="30" cy="42" rx="3.5" ry="2.5" fill="#7A4800" transform="rotate(-22 30 42)" />
          <circle  cx="72" cy="86" r="3"               fill="#5A3200" />
          <circle  cx="52" cy="36" r="2.5"             fill="#7A4800" opacity="0.8" />
          <circle  cx="22" cy="60" r="2"               fill="#6B4000" />
          <ellipse cx="80" cy="68" rx="3.5" ry="2.5" fill="#5A3200" transform="rotate(15 80 68)" />
          <ellipse cx="46" cy="108" rx="4" ry="2.5"  fill="#7A4800" transform="rotate(-5 46 108)" />
        </g>

        {/* ── Highlight — left-upper soft gleam ── */}
        <ellipse cx="34" cy="42" rx="11" ry="18"
          fill="white" opacity="0.20" transform="rotate(-24 34 42)" />
        <ellipse cx="28" cy="34" rx="4.5" ry="7"
          fill="white" opacity="0.32" transform="rotate(-24 28 34)" />

        {/* ═══════════════════════════════════
            TOP CAP — flies off when cracked
            Crack line sits at roughly y=36
            ═══════════════════════════════════ */}
        <path d="M50 6
                 C64 6 76 14 83 26
                 Q72 20 50 20
                 Q28 20 17 26
                 C24 14 36 6 50 6 Z"
          fill="url(#dEggCap)"
          filter="url(#dEggTex)"
          style={{
            transformOrigin: '50px 13px',
            transform: cracked
              ? 'translateY(-55px) rotate(-28deg) translateX(-10px)'
              : 'translateY(0px) rotate(0deg)',
            transition: 'transform 0.32s cubic-bezier(0.34,1.5,0.64,1), opacity 0.22s',
            opacity: cracked ? 0 : 1,
          }}
        />

        {/* ═══════════════════════════════════
            CRACKS — jagged, branching, glowing
            ═══════════════════════════════════ */}
        {cracked && (
          <g>
            {/* Warm glow seeping through — wide soft layer first */}
            <path d="M50 20 L46 33 L54 42 L47 55 L56 65 L49 80"
              stroke="#FF8800" strokeWidth="7" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.28" />
            <path d="M46 33 L35 28 L28 36"
              stroke="#FF8800" strokeWidth="5" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.22" />
            <path d="M54 42 L66 36 L74 44"
              stroke="#FF8800" strokeWidth="5" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.22" />

            {/* Bright yellow inner glow line */}
            <path d="M50 20 L46 33 L54 42 L47 55 L56 65 L49 80"
              stroke="#FFD000" strokeWidth="2.5" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.70" />
            <path d="M46 33 L35 28 L28 36"
              stroke="#FFD000" strokeWidth="2" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.55" />
            <path d="M54 42 L66 36 L74 44"
              stroke="#FFD000" strokeWidth="2" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.55" />

            {/* Dark crack edges — the actual break */}
            <path d="M50 20 L46 33 L54 42 L47 55 L56 65 L49 80"
              stroke="#2A1400" strokeWidth="2" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.90" />
            <path d="M46 33 L35 28 L28 36"
              stroke="#2A1400" strokeWidth="1.6" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.85" />
            <path d="M54 42 L66 36 L74 44"
              stroke="#2A1400" strokeWidth="1.6" strokeLinecap="round"
              strokeLinejoin="round" fill="none" opacity="0.85" />

            {/* Hairline tertiary cracks */}
            <path d="M28 36 L23 46"
              stroke="#3D2000" strokeWidth="1.1" strokeLinecap="round" fill="none" opacity="0.65" />
            <path d="M74 44 L80 54"
              stroke="#3D2000" strokeWidth="1.1" strokeLinecap="round" fill="none" opacity="0.65" />
            <path d="M47 55 L40 62"
              stroke="#3D2000" strokeWidth="1" strokeLinecap="round" fill="none" opacity="0.55" />
            <path d="M56 65 L63 70"
              stroke="#3D2000" strokeWidth="1" strokeLinecap="round" fill="none" opacity="0.55" />

            {/* Impact burst — glowing dot at strike point */}
            <circle cx="50" cy="18" r="6"
              fill="#FFDD00" opacity="0.45" filter="url(#dCrackGlow)" />
            <circle cx="50" cy="18" r="2.5"
              fill="white" opacity="0.80" />
          </g>
        )}
      </svg>

      {/* ── 🦖 hatches from egg ─────────────────────────── */}
      <div style={{
        position:   'absolute',
        bottom:     0,
        fontSize:   size * 0.66 + 'px',
        lineHeight: 1,
        transform:  hatched
          ? 'scale(1) translateY(0)'
          : 'scale(0.04) translateY(26px)',
        opacity:    hatched ? 1 : 0,
        transition: 'transform 0.55s cubic-bezier(0.34,1.62,0.64,1) 0.06s, opacity 0.28s 0.06s',
        filter:     hatched ? 'drop-shadow(0 5px 14px rgba(0,0,0,0.24))' : 'none',
        animation:  hatched ? 'dinoWiggle 0.7s ease 0.64s' : 'none',
      }}>🦖</div>

    </div>
  )
}


// ── Sign-In Screen ─────────────────────────────────────────────────────────────
// Reusable password input with eye toggle
function PwInput({ value, onChange, placeholder, style = {}, inputStyle = {}, id }) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ position:'relative', display:'flex', alignItems:'center', ...style }}>
      <input
        id={id}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete="current-password"
        style={{ ...inputStyle, paddingRight:'40px', width:'100%', boxSizing:'border-box' }}
      />
      <button
        type="button"
        onClick={()=>setShow(s=>!s)}
        tabIndex={-1}
        style={{
          position:'absolute', right:'10px',
          background:'none', border:'none', cursor:'pointer', padding:'2px',
          color:'#9CA3AF', fontSize:'16px', lineHeight:1, display:'flex', alignItems:'center',
        }}
        title={show ? 'Hide password' : 'Show password'}
      >
        {show ? '🙈' : '👁'}
      </button>
    </div>
  )
}

function LockScreen({ onUnlock }) {
  const C = useTheme()
  const [username,   setUsername]   = useState('')
  const [password,   setPassword]   = useState('')
  const [remember,   setRemember]   = useState(true)   // stay signed in
  const [error,      setError]      = useState('')
  const [loading,    setLoading]    = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [showForgot, setShowForgot] = useState(false)  // forgot-password modal

  // Forgot-password state
  const [fpIdentifier, setFpIdentifier] = useState('')
  const [fpLoading,    setFpLoading]    = useState(false)
  const [fpMsg,        setFpMsg]        = useState('')
  const [fpError,      setFpError]      = useState('')

  // Create User modal state
  const [cu, setCu] = useState({
    first_name:'', last_name:'', address:'', phone:'', email:'',
    username:'', password:'', confirm_password:'', role:'staff', admin_password:'',
  })
  const [cuError,   setCuError]   = useState('')
  const [cuSuccess, setCuSuccess] = useState('')
  const [cuLoading, setCuLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password) { setError('Please enter your username and password.'); return }
    setLoading(true); setError('')
    try {
      const r = await fetch(`${API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
      })
      const d = await r.json()
      if (!r.ok) { setError(d.detail || 'Sign in failed. Check your credentials.'); setLoading(false); return }
      // Persist session — localStorage keeps you signed in across restarts; sessionStorage clears on tab close
      const store = remember ? localStorage : sessionStorage
      const userObj = {
        username: d.username, first_name: d.first_name, last_name: d.last_name,
        role: d.role, panel_permissions: d.panel_permissions || []
      }
      store.setItem('rex-token', d.token)
      store.setItem('rex-user', JSON.stringify(userObj))
      // Also write to sessionStorage so /api/auth/me works in the same session
      sessionStorage.setItem('rex-token', d.token)
      sessionStorage.setItem('rex-user', JSON.stringify(userObj))
      onUnlock(d)
    } catch {
      setError('Cannot connect to REX. Make sure the system is running.')
    }
    setLoading(false)
  }

  const handleForgotPassword = async (e) => {
    e.preventDefault()
    if (!fpIdentifier.trim()) { setFpError('Please enter your username or email.'); return }
    setFpLoading(true); setFpError(''); setFpMsg('')
    try {
      const r = await fetch(`${API}/api/auth/forgot-password`, {
        method:'POST', headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ username: fpIdentifier.trim().toLowerCase() }),
      })
      const d = await r.json()
      if (!r.ok) { setFpError(d.detail || 'Request failed.'); }
      else       { setFpMsg(d.message || 'Check your email for the temporary password.') }
    } catch {
      setFpError('Cannot connect to REX.')
    }
    setFpLoading(false)
  }

  const handleCreateUser = async (e) => {
    e.preventDefault()
    setCuError(''); setCuSuccess('')
    if (!cu.first_name || !cu.last_name) { setCuError('First and last name are required.'); return }
    if (!cu.username)    { setCuError('Username is required.'); return }
    if (cu.password.length < 6) { setCuError('Password must be at least 6 characters.'); return }
    if (cu.password !== cu.confirm_password) { setCuError('Passwords do not match.'); return }
    if (!cu.admin_password) { setCuError('Admin (Chairman) password is required to create users.'); return }
    setCuLoading(true)
    try {
      const r = await fetch(`${API}/api/auth/create-user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: cu.username, password: cu.password,
          first_name: cu.first_name, last_name: cu.last_name,
          address: cu.address, phone: cu.phone, email: cu.email,
          role: cu.role, admin_password: cu.admin_password,
        }),
      })
      const d = await r.json()
      if (!r.ok) { setCuError(d.detail || 'Failed to create user.'); setCuLoading(false); return }
      setCuSuccess(`✅ User "${cu.username}" created successfully! They can now sign in.`)
      setCu({ first_name:'', last_name:'', address:'', phone:'', email:'', username:'', password:'', confirm_password:'', role:'staff', admin_password:'' })
    } catch {
      setCuError('Cannot connect to REX.')
    }
    setCuLoading(false)
  }

  const inputStyle = {
    width:'100%', boxSizing:'border-box', padding:'11px 14px', borderRadius:'10px',
    border:`1.5px solid ${C.border}`, fontSize:'14px', color:C.text, background:C.white,
    outline:'none', transition:'border-color 0.2s', fontFamily:'inherit',
  }
  const fieldStyle = { display:'flex', flexDirection:'column', gap:'5px' }
  const labelStyle = { fontSize:'12px', fontWeight:600, color:C.textMid }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:9999,
      background:`linear-gradient(135deg, #0f1e3c 0%, #1a2f5a 50%, #0f1e3c 100%)`,
      display:'flex', alignItems:'center', justifyContent:'center',
      fontFamily:"'Inter', system-ui, sans-serif",
    }}>
      {/* Gold particles bg */}
      <div style={{ position:'absolute', inset:0, overflow:'hidden', pointerEvents:'none' }}>
        {[...Array(12)].map((_,i) => (
          <div key={i} style={{
            position:'absolute',
            width: `${4 + (i%3)*3}px`, height: `${4 + (i%3)*3}px`,
            borderRadius:'50%', background:'rgba(201,168,76,0.15)',
            top:`${8 + i*7}%`, left:`${5 + i*8}%`,
            animation:`pulse ${2 + i*0.3}s ease-in-out infinite alternate`,
          }} />
        ))}
      </div>

      {/* Card */}
      <div style={{
        background:'rgba(255,255,255,0.97)', borderRadius:'20px',
        padding:'40px 36px', width:'100%', maxWidth:'420px', margin:'16px',
        boxShadow:'0 32px 80px rgba(0,0,0,0.5)',
        position:'relative', zIndex:1,
      }}>
        {/* Logo */}
        <div style={{ textAlign:'center', marginBottom:'28px' }}>
          <div style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:'64px', height:'64px', borderRadius:'18px', background:'linear-gradient(135deg,#1a2f5a,#0f1e3c)', marginBottom:'14px', boxShadow:'0 8px 24px rgba(0,0,0,0.2)' }}>
            <GoldEgg phase={1} size={40} />
          </div>
          <div style={{ fontWeight:800, fontSize:'22px', color:'#0f1e3c', letterSpacing:'-0.5px' }}>Gold Health Systems</div>
          <div style={{ fontSize:'12px', color:'#8899AA', marginTop:'4px', fontWeight:500 }}>REX Staff Portal · HIPAA Compliant</div>
        </div>

        {/* Sign-in form */}
        <form onSubmit={handleLogin} style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>Username</label>
            <input style={inputStyle} value={username} onChange={e=>setUsername(e.target.value)}
              placeholder="Enter your username" autoComplete="username" autoFocus />
          </div>
          <div style={fieldStyle}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <label style={labelStyle}>Password</label>
              <button type="button" onClick={()=>{ setShowForgot(true); setFpMsg(''); setFpError(''); setFpIdentifier(username) }}
                style={{ background:'none', border:'none', fontSize:'11px', color:'#C9A84C', cursor:'pointer', fontWeight:600, padding:0 }}>
                Forgot password?
              </button>
            </div>
            <PwInput
              value={password}
              onChange={e=>setPassword(e.target.value)}
              placeholder="Enter your password"
              inputStyle={inputStyle}
            />
          </div>

          {/* Remember me */}
          <label style={{ display:'flex', alignItems:'center', gap:'8px', cursor:'pointer', fontSize:'13px', color:'#4B5563' }}>
            <input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}
              style={{ width:'16px', height:'16px', accentColor:'#C9A84C', cursor:'pointer' }} />
            Keep me signed in
          </label>

          {error && (
            <div style={{ background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'8px', padding:'10px 13px', fontSize:'13px', color:'#DC2626' }}>
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            padding:'13px', borderRadius:'10px', border:'none', cursor:'pointer',
            background: loading ? '#9CA3AF' : 'linear-gradient(135deg,#C9A84C,#A8872D)',
            color:'#fff', fontSize:'15px', fontWeight:700, marginTop:'4px',
            boxShadow: loading ? 'none' : '0 4px 16px rgba(201,168,76,0.4)',
            transition:'all 0.2s',
          }}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        {/* Divider */}
        <div style={{ display:'flex', alignItems:'center', gap:'12px', margin:'20px 0' }}>
          <div style={{ flex:1, height:'1px', background:C.border }} />
          <div style={{ fontSize:'11px', color:C.textMuted, whiteSpace:'nowrap' }}>New Employee?</div>
          <div style={{ flex:1, height:'1px', background:C.border }} />
        </div>

        {/* Create User button */}
        <button onClick={()=>{ setShowCreate(true); setError('') }} style={{
          width:'100%', padding:'11px', borderRadius:'10px',
          border:`1.5px solid #1a2f5a`, background:'transparent',
          color:'#1a2f5a', fontSize:'14px', fontWeight:600, cursor:'pointer',
          transition:'all 0.2s',
        }}>
          + Create User Account
        </button>

        <div style={{ textAlign:'center', marginTop:'16px', fontSize:'11px', color:'#9CA3AF' }}>
          🔒 All access is logged · HIPAA §164.312(b)
        </div>
      </div>

      {/* ── Forgot Password Modal ── */}
      {showForgot && (
        <div style={{ position:'fixed', inset:0, zIndex:10001, background:'rgba(0,0,0,0.65)', backdropFilter:'blur(4px)',
          display:'flex', alignItems:'center', justifyContent:'center', padding:'16px' }}
          onClick={e=>{ if(e.target===e.currentTarget){ setShowForgot(false) } }}>
          <div style={{ background:'#fff', borderRadius:'20px', padding:'32px', width:'100%', maxWidth:'400px', boxShadow:'0 32px 80px rgba(0,0,0,0.4)' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'20px' }}>
              <div>
                <div style={{ fontWeight:800, fontSize:'18px', color:'#0f1e3c' }}>🔐 Forgot Password</div>
                <div style={{ fontSize:'12px', color:'#9CA3AF', marginTop:'3px' }}>A temporary password will be emailed to the recovery address</div>
              </div>
              <button onClick={()=>setShowForgot(false)} style={{ background:'none', border:'none', fontSize:'22px', color:'#9CA3AF', cursor:'pointer' }}>×</button>
            </div>

            {fpMsg ? (
              <div>
                <div style={{ background:'#ECFDF5', border:'1px solid #6EE7B7', borderRadius:'10px', padding:'14px 16px', fontSize:'13px', color:'#059669', marginBottom:'16px' }}>
                  ✅ {fpMsg}
                </div>
                <button onClick={()=>setShowForgot(false)} style={{ width:'100%', padding:'11px', borderRadius:'10px', border:'none',
                  background:'linear-gradient(135deg,#C9A84C,#A8872D)', color:'#fff', fontSize:'14px', fontWeight:700, cursor:'pointer' }}>
                  Back to Sign In
                </button>
              </div>
            ) : (
              <form onSubmit={handleForgotPassword} style={{ display:'flex', flexDirection:'column', gap:'14px' }}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Your Username or Email</label>
                  <input style={inputStyle} value={fpIdentifier} onChange={e=>setFpIdentifier(e.target.value)}
                    placeholder="e.g. jsmith or jsmith@goldhealthsys.com" autoFocus />
                </div>
                {fpError && <div style={{ background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'8px', padding:'10px 13px', fontSize:'13px', color:'#DC2626' }}>{fpError}</div>}
                <button type="submit" disabled={fpLoading} style={{ padding:'12px', borderRadius:'10px', border:'none', cursor:'pointer',
                  background: fpLoading ? '#9CA3AF' : 'linear-gradient(135deg,#1a2f5a,#0f1e3c)',
                  color:'#fff', fontSize:'14px', fontWeight:700 }}>
                  {fpLoading ? 'Sending…' : 'Send Temporary Password'}
                </button>
                <div style={{ textAlign:'center', fontSize:'11px', color:'#9CA3AF' }}>
                  The temporary password is always sent to the Chairman's recovery email for security.
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── Create User Modal ── */}
      {showCreate && (
        <div style={{
          position:'fixed', inset:0, zIndex:10000,
          background:'rgba(0,0,0,0.6)', backdropFilter:'blur(4px)',
          display:'flex', alignItems:'center', justifyContent:'center', padding:'16px',
        }} onClick={e=>{ if(e.target===e.currentTarget) setShowCreate(false) }}>
          <div style={{
            background:'#fff', borderRadius:'20px', padding:'32px',
            width:'100%', maxWidth:'480px', maxHeight:'90vh', overflowY:'auto',
            boxShadow:'0 32px 80px rgba(0,0,0,0.4)',
          }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px' }}>
              <div>
                <div style={{ fontWeight:800, fontSize:'18px', color:'#0f1e3c' }}>Create Staff Account</div>
                <div style={{ fontSize:'12px', color:'#9CA3AF', marginTop:'3px' }}>Requires Chairman admin password</div>
              </div>
              <button onClick={()=>setShowCreate(false)} style={{ background:'none', border:'none', fontSize:'22px', color:'#9CA3AF', cursor:'pointer', lineHeight:1 }}>×</button>
            </div>

            <form onSubmit={handleCreateUser} style={{ display:'flex', flexDirection:'column', gap:'14px' }}>
              {/* Name row */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px' }}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>First Name *</label>
                  <input style={inputStyle} value={cu.first_name} onChange={e=>setCu(p=>({...p,first_name:e.target.value}))} placeholder="First name" />
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Last Name *</label>
                  <input style={inputStyle} value={cu.last_name} onChange={e=>setCu(p=>({...p,last_name:e.target.value}))} placeholder="Last name" />
                </div>
              </div>

              {/* Address */}
              <div style={fieldStyle}>
                <label style={labelStyle}>Address</label>
                <input style={inputStyle} value={cu.address} onChange={e=>setCu(p=>({...p,address:e.target.value}))} placeholder="Street address, Brooklyn, NY" />
              </div>

              {/* Phone + Email */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px' }}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Phone</label>
                  <input style={inputStyle} value={cu.phone} onChange={e=>setCu(p=>({...p,phone:e.target.value}))} placeholder="(718) 555-0100" />
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Email</label>
                  <input style={inputStyle} type="email" value={cu.email} onChange={e=>setCu(p=>({...p,email:e.target.value}))} placeholder="email@example.com" />
                </div>
              </div>

              <div style={{ height:'1px', background:C.border, margin:'4px 0' }} />

              {/* Username + Role */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px' }}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Username *</label>
                  <input style={inputStyle} value={cu.username} onChange={e=>setCu(p=>({...p,username:e.target.value.toLowerCase().replace(/\s/g,'')}))} placeholder="e.g. jsmith" />
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Role</label>
                  <select style={{...inputStyle, cursor:'pointer'}} value={cu.role} onChange={e=>setCu(p=>({...p,role:e.target.value}))}>
                    <option value="staff">Staff</option>
                    <option value="driver">Driver</option>
                    <option value="supervisor">Supervisor</option>
                    <option value="chairman">Chairman</option>
                  </select>
                </div>
              </div>

              {/* Password — with eye toggles */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'12px' }}>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Password *</label>
                  <PwInput value={cu.password} onChange={e=>setCu(p=>({...p,password:e.target.value}))} placeholder="Min 6 characters" inputStyle={inputStyle} />
                </div>
                <div style={fieldStyle}>
                  <label style={labelStyle}>Confirm Password *</label>
                  <PwInput value={cu.confirm_password} onChange={e=>setCu(p=>({...p,confirm_password:e.target.value}))} placeholder="Repeat password" inputStyle={inputStyle} />
                </div>
              </div>

              <div style={{ height:'1px', background:C.border, margin:'4px 0' }} />

              {/* Admin password — with eye toggle */}
              <div style={fieldStyle}>
                <label style={labelStyle}>Chairman Admin Password *</label>
                <PwInput
                  value={cu.admin_password}
                  onChange={e=>setCu(p=>({...p,admin_password:e.target.value}))}
                  placeholder="Required to authorize new accounts"
                  inputStyle={{...inputStyle, borderColor:'#C9A84C'}}
                />
                <div style={{ fontSize:'11px', color:'#9CA3AF' }}>Default: chairman2026 (change this in settings)</div>
              </div>

              {cuError && <div style={{ background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'8px', padding:'10px 13px', fontSize:'13px', color:'#DC2626' }}>{cuError}</div>}
              {cuSuccess && <div style={{ background:'#ECFDF5', border:'1px solid #6EE7B7', borderRadius:'8px', padding:'10px 13px', fontSize:'13px', color:'#059669' }}>{cuSuccess}</div>}

              <div style={{ display:'flex', gap:'10px', marginTop:'4px' }}>
                <button type="button" onClick={()=>setShowCreate(false)} style={{
                  flex:1, padding:'12px', borderRadius:'10px', border:`1.5px solid ${C.border}`,
                  background:'transparent', color:C.textMid, fontSize:'14px', fontWeight:600, cursor:'pointer',
                }}>Cancel</button>
                <button type="submit" disabled={cuLoading} style={{
                  flex:2, padding:'12px', borderRadius:'10px', border:'none',
                  background: cuLoading ? '#9CA3AF' : 'linear-gradient(135deg,#1a2f5a,#0f1e3c)',
                  color:'#fff', fontSize:'14px', fontWeight:700, cursor:'pointer',
                  boxShadow:'0 4px 16px rgba(26,47,90,0.3)',
                }}>{cuLoading ? 'Creating…' : 'Create Account'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Secure Toggle ──────────────────────────────────────────────────────────────
function SecureToggle({ secure, onToggle }) {
  const C = useTheme()
  return (
    <button
      onClick={onToggle}
      style={{
        display:'flex', alignItems:'center', gap:'7px',
        padding:'8px 14px', borderRadius:'20px',
        background: secure ? C.secure : C.bgSecondary,
        border:`1px solid ${secure ? C.secure : C.border}`,
        color: secure ? '#fff' : C.textMid,
        fontSize:'13px', fontWeight:600,
        transition:'all 0.25s',
        minHeight:'38px',
        whiteSpace:'nowrap',
      }}
    >
      <span>{secure ? '🛡' : '🔓'}</span>
      <span style={{ display: window.innerWidth < 480 ? 'none' : 'inline' }}>
        {secure ? 'HIPAA' : 'Standard'}
      </span>
    </button>
  )
}

// ── Model Selector ─────────────────────────────────────────────────────────────
function ModelSelector({ models, selected, onSelect }) {
  const C = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const fn = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', fn)
    document.addEventListener('touchstart', fn)
    return () => { document.removeEventListener('mousedown', fn); document.removeEventListener('touchstart', fn) }
  }, [])
  const current = models.find(m => m.id === selected)
  const byProvider = models.reduce((a, m) => { (a[m.provider] ??= []).push(m); return a }, {})

  return (
    <div ref={ref} style={{ position:'relative', flexShrink:0 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display:'flex', alignItems:'center', gap:'7px',
          padding:'8px 12px', borderRadius:'10px',
          background: C.white,
          border:`1px solid ${open ? C.blue : C.border}`,
          color:C.text, fontSize:'13px', fontWeight:500,
          minWidth:'140px', maxWidth:'200px',
          justifyContent:'space-between',
          minHeight:'38px',
          boxShadow: open ? `0 0 0 3px rgba(0,102,255,0.12)` : 'none',
        }}
      >
        <span style={{ display:'flex', alignItems:'center', gap:'6px', overflow:'hidden' }}>
          <span>{PROVIDER_META[current?.provider]?.icon || '●'}</span>
          <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {current?.name || 'Select model'}
          </span>
          {current?.local && <span style={{ fontSize:'9px', background:'#E6F4EA', color:'#1A7F37', padding:'1px 5px', borderRadius:'4px', flexShrink:0 }}>LOCAL</span>}
        </span>
        <span style={{ color:C.textMuted, fontSize:'10px', flexShrink:0 }}>▾</span>
      </button>

      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 6px)', left:0,
          minWidth:'240px', background:C.white,
          border:`1px solid ${C.border}`,
          borderRadius:'14px',
          boxShadow:'0 8px 32px rgba(0,0,0,0.12)',
          zIndex:1000, overflow:'hidden',
          maxHeight:'60vh', overflowY:'auto',
        }}>
          {Object.entries(byProvider).map(([provider, pModels]) => {
            const meta = PROVIDER_META[provider] || { label:provider, color:C.textMid, icon:'●' }
            return (
              <div key={provider}>
                <div style={{
                  padding:'10px 14px 5px',
                  fontSize:'10px', fontWeight:700,
                  color:meta.color, letterSpacing:'0.8px',
                  textTransform:'uppercase',
                  background:'#FAFBFC',
                  borderBottom:`1px solid ${C.border}`,
                }}>
                  {meta.icon} {meta.label}
                </div>
                {pModels.map(m => (
                  <button
                    key={m.id}
                    onClick={() => { onSelect(m.id); setOpen(false) }}
                    style={{
                      display:'flex', alignItems:'center', justifyContent:'space-between',
                      width:'100%', padding:'12px 14px', textAlign:'left',
                      background: m.id === selected ? C.blueLight : 'transparent',
                      color:C.text, fontSize:'14px',
                      cursor:'pointer', border:'none',
                      minHeight:'44px',
                    }}
                  >
                    <span style={{ opacity: m.available ? 1 : 0.65 }}>{m.name}</span>
                    <span style={{ display:'flex', gap:'5px', alignItems:'center' }}>
                      {m.local && <span style={{ fontSize:'9px', background:'#E6F4EA', color:'#1A7F37', padding:'1px 5px', borderRadius:'4px' }}>LOCAL</span>}
                      {!m.available && !m.local && <span style={{ fontSize:'9px', background:'#FFF3CD', color:'#856404', padding:'1px 5px', borderRadius:'4px', border:'1px solid #FFD84D' }}>add key</span>}
                      {m.id === selected && <span style={{ color:C.blue, fontWeight:700 }}>✓</span>}
                    </span>
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Thinking dots ──────────────────────────────────────────────────────────────
function ThinkingDots() {
  const C = useTheme()
  return (
    <div style={{ display:'flex', gap:'5px', alignItems:'center', padding:'2px 0' }}>
      {[0,1,2].map(i => (
        <div key={i} style={{
          width:'6px', height:'6px', borderRadius:'50%',
          background:C.blue, opacity:0.6,
          animation:`pulse 1.2s ease-in-out ${i*0.2}s infinite`,
        }} />
      ))}
    </div>
  )
}

// ── Message Bubble ─────────────────────────────────────────────────────────────
function MessageBubble({ msg, secure, density = 'comfortable' }) {
  const C = useTheme()
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display:'flex', flexDirection:'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      marginBottom:'16px',
    }}>
      <div style={{
        display:'flex', alignItems:'center', gap:'6px',
        marginBottom:'4px', fontSize:'11px', color:C.textMuted,
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}>
        {(() => {
          const isRexxieMsg = !isUser && msg.model === 'rexxie-engine'
          return (
            <span style={{
              width:'20px', height:'20px', borderRadius:'50%',
              background: isUser ? C.blueLight : isRexxieMsg ? C.rexxieLight : C.bgSecondary,
              border:`1px solid ${isUser ? C.blue : isRexxieMsg ? C.rexxieMid : C.border}`,
              display:'flex', alignItems:'center', justifyContent:'center',
              fontSize:'10px', color: isUser ? C.blue : isRexxieMsg ? C.rexxie : C.textMid,
              fontWeight:700, flexShrink:0,
            }}>{isUser ? 'K' : isRexxieMsg ? '🐢' : '🦖'}</span>
          )
        })()}
        <span style={{ fontWeight:500 }}>{isUser ? 'Kato' : msg.model === 'rexxie-engine' ? 'Rexxie' : (msg.model?.split('/').pop()?.replace(/-/g,' ') || 'REX')}</span>
        {msg.timestamp && <span>{fmt(msg.timestamp)}</span>}
        {msg.phi_detected && (
          <span style={{
            background:'#E6EDFC', color:C.secure,
            border:'1px solid rgba(16,69,184,0.2)',
            borderRadius:'8px', padding:'1px 7px', fontSize:'10px',
          }}>🛡 PHI shielded</span>
        )}
      </div>
      {(() => {
        const isRexxieBubble = !isUser && msg.model === 'rexxie-engine'
        return (
      <div style={{
        maxWidth:'82%',
        padding: DENSITY_PAD[density] || '11px 14px',
        borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
        background: isUser ? (secure ? C.secureLight : C.blueLight) : isRexxieBubble ? C.rexxieLight : C.white,
        border:`1px solid ${isUser ? (secure ? 'rgba(16,69,184,0.2)' : C.blueMid) : isRexxieBubble ? C.rexxieMid : C.border}`,
        boxShadow: isRexxieBubble ? '0 1px 3px rgba(155,79,114,0.08)' : '0 1px 3px rgba(0,0,0,0.06)',
        fontSize:'14px', lineHeight:1.65, color:C.text,
        wordBreak:'break-word',
      }}>
        {msg.streaming ? <ThinkingDots /> :
         isUser ? <span style={{ whiteSpace:'pre-wrap' }}>{msg.content}</span> :
         <div className="prose"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>}
      </div>
        )
      })()}
    </div>
  )
}

// ── Folder helpers ─────────────────────────────────────────────────────────────
function loadFolders() {
  try { return JSON.parse(localStorage.getItem('rex-folders') || '{}') } catch { return {} }
}
function saveFolders(f) {
  try { localStorage.setItem('rex-folders', JSON.stringify(f)) } catch {}
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar({ journeys, currentId, onSelect, onNew, onClose, eggPhase = 1, rexxieMode = false, onToggleRexxie, toggleDisabled }) {
  const C = useTheme()
  const isMobile = useIsMobile()

  const [folders, setFolders]       = useState(loadFolders)
  const [rextFolder, setRextFolder] = useState(() => {
    try { return JSON.parse(localStorage.getItem('rex-rext-folders') || '{}') } catch { return {} }
  })
  const [editingFolder, setEditingFolder] = useState(null)
  const [folderDraft, setFolderDraft]     = useState('')
  const [dragging, setDragging]           = useState(null)

  const persistFolders = (f)  => { setFolders(f); saveFolders(f) }
  const persistRF      = (rf) => { setRextFolder(rf); try { localStorage.setItem('rex-rext-folders', JSON.stringify(rf)) } catch {} }

  const addFolder = () => {
    const id = 'folder_' + Date.now()
    const name = 'New Folder'
    persistFolders({ ...folders, [id]: { name, open: true } })
    setEditingFolder(id); setFolderDraft(name)
  }
  const renameFolder = (id, name) => { persistFolders({ ...folders, [id]: { ...folders[id], name } }); setEditingFolder(null) }
  const toggleFolderOpen = (id)   => { persistFolders({ ...folders, [id]: { ...folders[id], open: !folders[id].open } }) }
  const deleteFolder = (id) => {
    const rf = { ...rextFolder }
    Object.keys(rf).forEach(k => { if (rf[k] === id) delete rf[k] })
    persistRF(rf)
    const f = { ...folders }; delete f[id]; persistFolders(f)
  }
  const moveToFolder = (jid, fid) => {
    const rf = { ...rextFolder }
    if (!fid) { delete rf[jid] } else { rf[jid] = fid }
    persistRF(rf)
  }

  const unfoldered = journeys.filter(j => !rextFolder[j.id])
  const grouped    = Object.entries(folders).reduce((acc, [fid, fd]) => {
    acc[fid] = { ...fd, items: journeys.filter(j => rextFolder[j.id] === fid) }
    return acc
  }, {})

  const RextItem = ({ j }) => (
    <div draggable onDragStart={() => setDragging(j.id)} onDragEnd={() => setDragging(null)}
      style={{ position:'relative', marginBottom:'2px' }}>
      <button onClick={() => { onSelect(j.id); onClose?.() }} style={{
        width:'100%', padding:'9px 10px', borderRadius:'10px', textAlign:'left',
        background: j.id === currentId
          ? (rexxieMode ? `linear-gradient(135deg,${C.rexxieLight},${C.rexxieMid}40)` : `linear-gradient(135deg,${C.blueLight},${C.blueMid}50)`)
          : 'transparent',
        color:C.text, fontSize:'13px',
        display:'flex', flexDirection:'column', gap:'2px',
        border:`1px solid ${j.id === currentId ? (rexxieMode ? C.rexxieMid : C.blue) : 'transparent'}`,
        minHeight:'42px', transition:'all 0.18s',
        boxShadow: j.id === currentId ? '0 2px 8px rgba(0,0,0,0.06)' : 'none',
      }}>
        <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', fontWeight: j.id === currentId ? 600 : 400, fontSize:'13px' }}>
          {j.secure_mode && '🛡 '}{j.title || 'Untitled Rext'}
        </span>
        <span style={{ color:C.textMuted, fontSize:'10px' }}>{j.message_count} msg · {j.created_at?.slice(0,10)}</span>
      </button>
      {Object.keys(folders).length > 0 && (
        <select value={rextFolder[j.id] || ''} onChange={e => moveToFolder(j.id, e.target.value)}
          onClick={e => e.stopPropagation()}
          style={{
            position:'absolute', right:'4px', top:'50%', transform:'translateY(-50%)',
            fontSize:'10px', background:C.bgSecondary, border:`1px solid ${C.border}`,
            borderRadius:'5px', color:C.textMuted, padding:'1px 3px', cursor:'pointer',
            opacity: j.id === currentId ? 1 : 0, maxWidth:'72px', transition:'opacity 0.2s',
          }}>
          <option value="">— none —</option>
          {Object.entries(folders).map(([fid, fd]) => <option key={fid} value={fid}>{fd.name}</option>)}
        </select>
      )}
    </div>
  )

  return (
    <div style={{
      width:'240px', flexShrink:0, height:'100dvh',
      background:C.white, borderRight:`1px solid ${C.border}`,
      display:'flex', flexDirection:'column', overflow:'hidden',
      position:'fixed', top:0, left:0, bottom:0,
      boxShadow: isMobile ? '6px 0 28px rgba(0,0,0,0.15)' : '1px 0 0 rgba(0,0,0,0.06)',
      ...(isMobile ? { zIndex:500, width:'80vw', maxWidth:'280px' } : {}),
    }}>
      {/* Logo row */}
      <div style={{
        padding:'14px 14px 12px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', gap:'8px',
        background: rexxieMode
          ? `linear-gradient(135deg,${C.rexxieLight},${C.white})`
          : `linear-gradient(135deg,${C.blueLight}50,${C.white})`,
        transition:'background 0.4s',
      }}>
        <GoldEgg phase={eggPhase} size={30} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontWeight:800, fontSize:'15px', letterSpacing:'-0.4px', color: rexxieMode ? C.rexxie : C.text, transition:'color 0.3s' }}>
            {rexxieMode ? 'Rexxie' : 'REX'}
          </div>
          <div style={{ fontSize:'10px', color:C.textMuted }}>{rexxieMode ? 'Private mode' : 'Privacy Proxy'}</div>
        </div>
        <span style={{
          fontSize:'10px', fontWeight:700,
          background: rexxieMode ? C.rexxieLight : C.blueLight,
          color: rexxieMode ? C.rexxie : C.blue,
          padding:'3px 8px', borderRadius:'12px',
        }}>v3</span>
        {isMobile && (
          <button onClick={onClose} style={{ width:'28px', height:'28px', borderRadius:'50%', background:C.bgSecondary, color:C.textMid, fontSize:'14px', display:'flex', alignItems:'center', justifyContent:'center' }}>✕</button>
        )}
      </div>

      {/* New Rext button */}
      <div style={{ padding:'12px 12px 6px' }}>
        <button onClick={() => { onNew(); onClose?.() }} style={{
          width:'100%', padding:'11px 12px', borderRadius:'12px',
          background: rexxieMode ? `linear-gradient(135deg,${C.rexxie},${C.rexxieDark})` : `linear-gradient(135deg,${C.blue},${C.blueDark})`,
          color:'#fff', fontWeight:700, fontSize:'14px',
          display:'flex', alignItems:'center', gap:'8px', justifyContent:'center',
          boxShadow:`0 3px 12px ${rexxieMode ? 'rgba(155,79,114,0.32)' : 'rgba(0,102,255,0.28)'}`,
          minHeight:'44px', transition:'all 0.3s',
        }}>
          <span style={{ fontSize:'18px', lineHeight:1 }}>+</span>
          <span>{rexxieMode ? 'New Rexxie Rext' : 'New Rext'}</span>
        </button>
      </div>

      {/* REX ↔ Rexxie toggle */}
      <div style={{ padding:'0 12px 10px' }}>
        <RexxieProfileToggle rexxieMode={rexxieMode} onToggle={onToggleRexxie} disabled={toggleDisabled} />
      </div>

      {/* Rext list + folders */}
      <div style={{ flex:1, overflowY:'auto', padding:'0 8px 8px' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'6px 4px 6px', marginBottom:'2px' }}>
          <span style={{ fontSize:'10px', fontWeight:700, color:C.textMuted, letterSpacing:'0.8px', textTransform:'uppercase' }}>Rexts</span>
          <button onClick={addFolder} title="New folder" style={{ fontSize:'11px', color:C.textMuted, padding:'2px 7px', borderRadius:'6px', background:C.bgSecondary, border:`1px solid ${C.border}` }}>+ folder</button>
        </div>

        {/* Folders */}
        {Object.entries(grouped).map(([fid, fdata]) => (
          <div key={fid} style={{ marginBottom:'4px' }}
            onDragOver={e => e.preventDefault()}
            onDrop={() => { moveToFolder(dragging, fid); setDragging(null) }}>
            <div style={{ display:'flex', alignItems:'center', padding:'5px 8px', borderRadius:'8px', background:C.bgSecondary, border:`1px solid ${C.border}`, marginBottom:'2px', cursor:'pointer' }}>
              <span onClick={() => toggleFolderOpen(fid)} style={{ flex:1, display:'flex', alignItems:'center', gap:'6px', fontSize:'12px', fontWeight:600, color:C.textMid }}>
                <span style={{ fontSize:'10px', display:'inline-block', transform: fdata.open ? 'rotate(90deg)' : 'none', transition:'transform 0.2s' }}>▶</span>
                <span>📁</span>
                {editingFolder === fid
                  ? <input autoFocus value={folderDraft} onChange={e => setFolderDraft(e.target.value)}
                      onBlur={() => renameFolder(fid, folderDraft || 'Folder')}
                      onKeyDown={e => e.key === 'Enter' && renameFolder(fid, folderDraft || 'Folder')}
                      onClick={e => e.stopPropagation()}
                      style={{ background:'transparent', border:'none', outline:'none', fontWeight:600, fontSize:'12px', color:C.text, width:'80px' }} />
                  : <span onDoubleClick={() => { setEditingFolder(fid); setFolderDraft(fdata.name) }}>{fdata.name}</span>
                }
                <span style={{ fontSize:'10px', color:C.textMuted }}>({fdata.items.length})</span>
              </span>
              <button onClick={() => deleteFolder(fid)} title="Delete folder" style={{ fontSize:'11px', color:C.textMuted, padding:'2px 4px' }}>✕</button>
            </div>
            {fdata.open && fdata.items.map(j => <RextItem key={j.id} j={j} />)}
          </div>
        ))}

        {/* Unfoldered Rexts */}
        <div onDragOver={e => e.preventDefault()} onDrop={() => { moveToFolder(dragging, null); setDragging(null) }}>
          {unfoldered.map(j => <RextItem key={j.id} j={j} />)}
        </div>

        {journeys.length === 0 && (
          <div style={{ padding:'20px 8px', textAlign:'center', color:C.textMuted, fontSize:'12px', lineHeight:1.8 }}>
            Start a new Rext.<br/>All conversations are encrypted locally.
          </div>
        )}
      </div>

      <div style={{ padding:'10px 14px', borderTop:`1px solid ${C.border}`, fontSize:'10px', color:C.textMuted, display:'flex', alignItems:'center', gap:'5px' }}>
        <span>🔐</span><span>AES-256 · Triple-layer · macOS Keychain</span>
      </div>
    </div>
  )
}

// ── Settings Modal ─────────────────────────────────────────────────────────────
function SettingsModal({ onClose, health, appearance, onAppearanceChange }) {
  const C = useTheme()
  const isMobile = useIsMobile()
  const [tab, setTab] = useState('appearance')
  const [provider, setProvider] = useState('anthropic')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [status, setStatus] = useState({})

  useEffect(() => {
    fetch(`${API}/api/keys/status`).then(r => r.json()).then(d => setStatus(d.providers)).catch(() => {})
  }, [])

  async function saveKey() {
    if (!apiKey.trim()) return
    setSaving(true)
    const r = await fetch(`${API}/api/keys`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ provider, api_key: apiKey }),
    })
    setSaving(false)
    if (r.ok) { setSaved(true); setApiKey(''); setTimeout(() => setSaved(false), 2500) }
  }

  const tabs = [{ id:'appearance', label:'🎨 Appearance' }, { id:'keys', label:'🔑 API Keys' }, { id:'system', label:'⚙ System' }]

  return (
    <div style={{
      position:'fixed', inset:0,
      background:'rgba(13,17,23,0.45)',
      display:'flex', alignItems: isMobile ? 'flex-end' : 'center',
      justifyContent:'center',
      zIndex:2000,
      backdropFilter:'blur(4px)',
    }} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{
        background:C.white,
        borderRadius: isMobile ? '20px 20px 0 0' : '16px',
        width: isMobile ? '100%' : '520px',
        maxHeight: isMobile ? '90vh' : '82vh',
        overflow:'hidden',
        display:'flex', flexDirection:'column',
        boxShadow:'0 8px 40px rgba(0,0,0,0.18)',
      }}>
        <div style={{ padding:'20px 20px 14px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>REX Settings</div>
            <div style={{ fontSize:'12px', color:C.textMuted, marginTop:'2px' }}>Privacy Proxy v2.0 · HIPAA Compliant</div>
          </div>
          <button onClick={onClose} style={{ width:'32px', height:'32px', borderRadius:'50%', background:C.bgSecondary, color:C.textMid, fontSize:'15px', display:'flex', alignItems:'center', justifyContent:'center' }}>✕</button>
        </div>

        <div style={{ display:'flex', gap:'2px', padding:'10px 16px 0', borderBottom:`1px solid ${C.border}` }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding:'8px 16px', fontSize:'14px', fontWeight:500,
              color: tab === t.id ? C.blue : C.textMid,
              borderBottom:`2px solid ${tab === t.id ? C.blue : 'transparent'}`,
              marginBottom:'-1px', minHeight:'44px',
            }}>{t.label}</button>
          ))}
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:'20px' }}>
          {tab === 'appearance' && appearance && (
            <div style={{ display:'flex', flexDirection:'column', gap:'22px' }}>

              {/* Font Size */}
              <div>
                <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.7px', textTransform:'uppercase', marginBottom:'10px' }}>Font Size</div>
                <div style={{ display:'flex', gap:'8px' }}>
                  {[{ id:'small', label:'A', size:13 }, { id:'medium', label:'A', size:15 }, { id:'large', label:'A', size:17 }, { id:'xlarge', label:'A', size:19 }].map(opt => (
                    <button key={opt.id} onClick={() => onAppearanceChange({ ...appearance, fontSize: opt.size })}
                      style={{ flex:1, padding:'10px 6px', borderRadius:'10px', fontSize: opt.size + 'px', fontWeight:600,
                        background: appearance.fontSize === opt.size ? C.blue : C.bgSecondary,
                        color: appearance.fontSize === opt.size ? '#fff' : C.textMid,
                        border:`1.5px solid ${appearance.fontSize === opt.size ? C.blue : C.border}`,
                        minHeight:'48px', transition:'all 0.2s',
                      }}>{opt.label}</button>
                  ))}
                </div>
                <div style={{ fontSize:'12px', color:C.textMuted, marginTop:'6px' }}>Current: {appearance.fontSize}px</div>
              </div>

              {/* Theme */}
              <div>
                <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.7px', textTransform:'uppercase', marginBottom:'10px' }}>Theme</div>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px' }}>
                  {[
                    { id:'light',    label:'☀️ Light',     preview:['#FFFFFF','#F5F6F8'] },
                    { id:'dark',     label:'🌙 Dark',      preview:['#161B22','#0D1117'] },
                    { id:'midnight', label:'🌌 Midnight',  preview:['#16213e','#1a1a2e'] },
                    { id:'warm',     label:'🍂 Warm',      preview:['#FFFCF5','#FDF8F0'] },
                    { id:'ocean',    label:'🌊 Ocean',     preview:['#0F1F3D','#0B1426'] },
                    { id:'forest',   label:'🌲 Forest',    preview:['#162018','#0F1A0E'] },
                    { id:'sunset',   label:'🌅 Sunset',    preview:['#240F2A','#1A0E1E'] },
                    { id:'custom',   label:'🎨 Custom',    preview:[(appearance.customColors?.white || '#fff'),(appearance.customColors?.bg || '#f5f5f5')] },
                  ].map(t => (
                    <button key={t.id} onClick={() => onAppearanceChange({ ...appearance, theme: t.id })}
                      style={{
                        padding:'10px 12px', borderRadius:'12px', textAlign:'left',
                        background: appearance.theme === t.id ? C.blueLight : C.bgSecondary,
                        border:`2px solid ${appearance.theme === t.id ? C.blue : C.border}`,
                        color: C.text, fontSize:'13px', fontWeight: appearance.theme === t.id ? 600 : 400,
                        display:'flex', alignItems:'center', gap:'8px', minHeight:'44px',
                        transition:'all 0.2s',
                      }}>
                      <span style={{ display:'flex', gap:'-4px' }}>
                        <span style={{ width:'14px', height:'14px', borderRadius:'50%', background:t.preview[0], border:`1px solid ${C.border}`, flexShrink:0 }}/>
                        <span style={{ width:'14px', height:'14px', borderRadius:'50%', background:t.preview[1], border:`1px solid ${C.border}`, flexShrink:0, marginLeft:'-6px' }}/>
                      </span>
                      {t.label}
                      {appearance.theme === t.id && <span style={{ marginLeft:'auto', color:C.blue }}>✓</span>}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom color editor — only shown when Custom theme is active */}
              {appearance.theme === 'custom' && (
                <div style={{ background:C.bgSecondary, borderRadius:'12px', padding:'14px', border:`1px solid ${C.border}` }}>
                  <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.7px', textTransform:'uppercase', marginBottom:'12px' }}>Custom Colors</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
                    {[
                      { key:'bg',     label:'Background' },
                      { key:'white',  label:'Card / Panel' },
                      { key:'accent', label:'Accent Color' },
                      { key:'text',   label:'Text' },
                    ].map(({ key, label }) => (
                      <div key={key} style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                        <span style={{ fontSize:'13px', color:C.textMid }}>{label}</span>
                        <div style={{ display:'flex', alignItems:'center', gap:'8px' }}>
                          <span style={{ fontSize:'11px', color:C.textMuted, fontFamily:'monospace' }}>
                            {(appearance.customColors?.[key] || '#000000').toUpperCase()}
                          </span>
                          <input
                            type="color"
                            value={appearance.customColors?.[key] || '#000000'}
                            onChange={e => onAppearanceChange({
                              ...appearance,
                              customColors: { ...appearance.customColors, [key]: e.target.value }
                            })}
                            style={{ width:'36px', height:'28px', borderRadius:'6px', border:`1px solid ${C.border}`, cursor:'pointer', padding:'1px' }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Accent Color — shown for non-custom themes */}
              {appearance.theme !== 'custom' && (
                <div>
                  <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.7px', textTransform:'uppercase', marginBottom:'10px' }}>Accent Color</div>
                  <div style={{ display:'flex', gap:'10px', flexWrap:'wrap' }}>
                    {[
                      { id:'blue',   color:'#0066FF', label:'Blue' },
                      { id:'gold',   color:'#c9a84c', label:'Gold' },
                      { id:'green',  color:'#1A7F37', label:'Green' },
                      { id:'purple', color:'#7B2FBE', label:'Purple' },
                      { id:'rose',   color:'#E11D48', label:'Rose' },
                      { id:'orange', color:'#EA580C', label:'Orange' },
                      { id:'teal',   color:'#0D9488', label:'Teal' },
                    ].map(a => (
                      <button key={a.id} onClick={() => onAppearanceChange({ ...appearance, accentColor: a.id })}
                        title={a.label}
                        style={{ width:'34px', height:'34px', borderRadius:'50%', background:a.color,
                          border:`3px solid ${appearance.accentColor === a.id ? C.text : 'transparent'}`,
                          boxShadow: appearance.accentColor === a.id ? `0 0 0 2px ${C.bg}, 0 0 0 4px ${a.color}` : 'none',
                          transition:'all 0.2s', flexShrink:0,
                        }}/>
                    ))}
                  </div>
                </div>
              )}

              {/* Message Density */}
              <div>
                <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.7px', textTransform:'uppercase', marginBottom:'10px' }}>Message Spacing</div>
                <div style={{ display:'flex', gap:'8px' }}>
                  {['compact', 'comfortable', 'spacious'].map(d => (
                    <button key={d} onClick={() => onAppearanceChange({ ...appearance, density: d })}
                      style={{ flex:1, padding:'10px 6px', borderRadius:'10px', fontSize:'13px', fontWeight:500,
                        background: appearance.density === d ? C.blue : C.bgSecondary,
                        color: appearance.density === d ? '#fff' : C.textMid,
                        border:`1.5px solid ${appearance.density === d ? C.blue : C.border}`,
                        minHeight:'44px', textTransform:'capitalize', transition:'all 0.2s',
                      }}>{d}</button>
                  ))}
                </div>
              </div>

              {/* Reset */}
              <button onClick={() => onAppearanceChange(DEFAULT_APPEARANCE)} style={{
                padding:'10px', borderRadius:'10px', fontSize:'13px',
                background:'transparent', border:`1px solid ${C.border}`,
                color:C.textMuted, minHeight:'44px',
              }}>Reset to Defaults</button>

            </div>
          )}

          {tab === 'keys' && (
            <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
              <div style={{ fontSize:'13px', color:C.textMid, lineHeight:1.6 }}>
                Keys stored in <strong>macOS Keychain</strong> — never written to disk.
              </div>

              {/* Provider cards — click to select */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px' }}>
                {[
                  { id:'anthropic',  label:'Claude',     icon:'⚡', color:'#CC5500', url:'https://console.anthropic.com',              hint:'Anthropic API key' },
                  { id:'openai',     label:'ChatGPT',    icon:'●',  color:'#10A37F', url:'https://platform.openai.com/api-keys',        hint:'OpenAI API key' },
                  { id:'google',     label:'Gemini',     icon:'◆',  color:'#4285F4', url:'https://aistudio.google.com/app/apikey',      hint:'Google AI Studio key' },
                  { id:'xai',        label:'Grok',       icon:'✴',  color:'#7B2FBE', url:'https://console.x.ai',                        hint:'xAI API key' },
                  { id:'perplexity', label:'Perplexity', icon:'🔍', color:'#20808D', url:'https://www.perplexity.ai/settings/api',       hint:'Perplexity API key' },
                  { id:'librechat',  label:'LibreChat',  icon:'🔗', color:'#E85D26', url:'http://localhost:3080',                        hint:'Optional: LibreChat auth token (leave blank if none)' },
                ].map(p => {
                  const has = status[p.id]
                  const sel = provider === p.id
                  return (
                    <button key={p.id} onClick={()=>setProvider(p.id)} style={{
                      padding:'10px 12px', borderRadius:'10px', textAlign:'left',
                      background: sel ? (C.dark ? '#1e2a3a' : '#EFF6FF') : C.bgSecondary,
                      border:`2px solid ${sel ? p.color : (has ? p.color+'44' : C.border)}`,
                      cursor:'pointer', transition:'all .15s',
                    }}>
                      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                        <span style={{ fontSize:'15px', color:p.color, fontWeight:700 }}>{p.icon} {p.label}</span>
                        <span style={{ fontSize:'11px', fontWeight:600, color: has ? '#16A34A' : C.textMuted }}>
                          {has ? '✓ Active' : '○ No key'}
                        </span>
                      </div>
                      <a href={p.url} target="_blank" rel="noreferrer"
                        onClick={e=>e.stopPropagation()}
                        style={{ fontSize:'10px', color:C.textMuted, textDecoration:'none' }}>
                        {p.url.replace('https://','').replace('http://','').split('/')[0]} ↗
                      </a>
                    </button>
                  )
                })}
              </div>

              {/* Key input */}
              <div style={{ fontSize:'11px', color:C.textMuted }}>
                {provider === 'librechat'
                  ? '🔗 LibreChat runs locally on port 3080. Leave blank to connect without auth, or paste a token if you enabled authentication in LibreChat settings.'
                  : `Paste your ${PROVIDER_META[provider]?.label || provider} API key below:`}
              </div>
              <PwInput
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={provider === 'librechat' ? 'LibreChat auth token (optional)…' : 'Paste API key…'}
                inputStyle={{
                  padding:'12px 40px 12px 12px', border:`1px solid ${apiKey ? C.blue : C.border}`,
                  borderRadius:'10px', background:C.white, fontSize:'15px',
                  minHeight:'44px', fontFamily:'monospace',
                }}
              />
              <button onClick={saveKey} disabled={!apiKey.trim() || saving} style={{
                padding:'14px', borderRadius:'10px',
                background: saved ? C.success : C.blue,
                color:'#fff', fontWeight:700, fontSize:'15px',
                opacity: !apiKey.trim() || saving ? 0.5 : 1,
                minHeight:'48px',
              }}>
                {saved ? '✓ Saved!' : saving ? 'Saving…' : `Save ${PROVIDER_META[provider]?.label || provider} Key`}
              </button>
            </div>
          )}

          {tab === 'system' && health && (
            <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
              {[
                ['De-ID Engine', health.deid_engine],
                ['Encryption', 'AES-256-GCM'],
                ['Key Storage', 'macOS Keychain'],
                ['Version', 'REX v2.0'],
                ['Key Fingerprint', health.key_fingerprint],
              ].map(([label, value]) => (
                <div key={label} style={{
                  display:'flex', justifyContent:'space-between', alignItems:'center',
                  padding:'12px 14px', background:C.bgSecondary,
                  borderRadius:'10px', border:`1px solid ${C.border}`, gap:'12px',
                }}>
                  <span style={{ fontSize:'13px', color:C.textMid, fontWeight:500, flexShrink:0 }}>{label}</span>
                  <span style={{ fontSize:'12px', color:C.text, fontFamily:'monospace', textAlign:'right', wordBreak:'break-all' }}>{value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Rexxie Profile Toggle — account switcher (chairman only) ──────────────────
function RexxieProfileToggle({ rexxieMode, onToggle, disabled }) {
  const C = useTheme()
  return (
    <div style={{
      display:'flex', alignItems:'center', width:'100%',
      background: rexxieMode ? C.rexxieLight : C.bgSecondary,
      border:`1.5px solid ${rexxieMode ? C.rexxieMid : C.border}`,
      borderRadius:'12px', padding:'3px',
      gap:'2px',
      transition:'all 0.3s',
      boxShadow: rexxieMode ? '0 2px 10px rgba(155,79,114,0.14)' : 'none',
    }}>
      {/* REX tab */}
      <button
        onClick={() => rexxieMode && !disabled && onToggle()}
        disabled={disabled || !rexxieMode}
        style={{
          flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'6px',
          padding:'7px 10px', borderRadius:'9px',
          background: !rexxieMode ? C.white : 'transparent',
          color: !rexxieMode ? C.blue : C.textMuted,
          fontWeight: !rexxieMode ? 700 : 500,
          fontSize:'13px',
          boxShadow: !rexxieMode ? '0 1px 4px rgba(0,0,0,0.10)' : 'none',
          transition:'all 0.2s',
          minHeight:'34px',
        }}
      >
        <span style={{ fontSize:'15px' }}>🦖</span>
        <span>REX</span>
      </button>
      {/* Rexxie tab */}
      <button
        onClick={() => !rexxieMode && !disabled && onToggle()}
        disabled={disabled || rexxieMode}
        style={{
          flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:'6px',
          padding:'7px 10px', borderRadius:'9px',
          background: rexxieMode ? C.white : 'transparent',
          color: rexxieMode ? C.rexxie : C.textMuted,
          fontWeight: rexxieMode ? 700 : 500,
          fontSize:'13px',
          boxShadow: rexxieMode ? '0 1px 6px rgba(155,79,114,0.18)' : 'none',
          transition:'all 0.2s',
          minHeight:'34px',
        }}
      >
        <span style={{ fontSize:'15px' }}>🐢</span>
        <span>Rexxie</span>
      </button>
    </div>
  )
}

// ── Compute merged theme tokens from appearance settings ───────────────────────
const EXTRA_ACCENTS = {
  purple:  { blue:'#7B2FBE', blueDark:'#6020A0', blueLight:'#F0E6F9', blueMid:'#D9BFED', secure:'#4A1480', secureLight:'#E8D5F5' },
  rose:    { blue:'#E11D48', blueDark:'#BE123C', blueLight:'#FFF1F3', blueMid:'#FECDD3', secure:'#9F1239', secureLight:'#FFE4E6' },
  orange:  { blue:'#EA580C', blueDark:'#C2410C', blueLight:'#FFF7ED', blueMid:'#FED7AA', secure:'#9A3412', secureLight:'#FFEDD5' },
  teal:    { blue:'#0D9488', blueDark:'#0F766E', blueLight:'#F0FDFA', blueMid:'#99F6E4', secure:'#134E4A', secureLight:'#CCFBF1' },
}
const WARM_TOKENS = {
  bg:'#FDF8F0', white:'#FFFCF5', bgSecondary:'#F5EFE0',
  text:'#2C1810', textMid:'#6B4C3B', textMuted:'#9B7A6A',
  border:'#E8D5C4',
}
const MIDNIGHT_TOKENS = {
  bg:'#1a1a2e', white:'#16213e', bgSecondary:'#1a1a3e',
  text:'#E8E8F0', textMid:'#8888AA', textMuted:'#6666AA',
  border:'#2d3561', blueLight:'#1a1a4e', blueMid:'#1a2260',
  rexxieLight:'#2A1030', rexxieMid:'#3D1848', rexxieBg:'#1a0f20',
}
const OCEAN_TOKENS = {
  bg:'#0B1426', white:'#0F1F3D', bgSecondary:'#152847',
  text:'#BAD4F5', textMid:'#6B9ACF', textMuted:'#4A6E9B',
  border:'#1E3A5F', blueLight:'#102040', blueMid:'#1a3060',
  rexxieLight:'#1a1030', rexxieMid:'#2d1848', rexxieBg:'#100d1a',
}
const FOREST_TOKENS = {
  bg:'#0F1A0E', white:'#162018', bgSecondary:'#1E2B1C',
  text:'#C8E6C0', textMid:'#6B9A60', textMuted:'#4A7040',
  border:'#2A4028', blueLight:'#142A10', blueMid:'#1E3E18',
}
const SUNSET_TOKENS = {
  bg:'#1A0E1E', white:'#240F2A', bgSecondary:'#2E1838',
  text:'#F5CEDC', textMid:'#C47090', textMuted:'#8A4060',
  border:'#3D1F45', blueLight:'#2A1030', blueMid:'#3A1848',
}

function computeTheme(appearance) {
  const base = { ...C }
  if (appearance.theme === 'dark')     Object.assign(base, DARK_TOKENS)
  if (appearance.theme === 'midnight') Object.assign(base, MIDNIGHT_TOKENS)
  if (appearance.theme === 'warm')     Object.assign(base, WARM_TOKENS)
  if (appearance.theme === 'ocean')    Object.assign(base, OCEAN_TOKENS)
  if (appearance.theme === 'forest')   Object.assign(base, FOREST_TOKENS)
  if (appearance.theme === 'sunset')   Object.assign(base, SUNSET_TOKENS)
  if (appearance.theme === 'custom' && appearance.customColors) {
    const cc = appearance.customColors
    Object.assign(base, {
      bg: cc.bg, bgSecondary: cc.bg,
      white: cc.white,
      text: cc.text,
      blue: cc.accent, blueDark: cc.accent, secure: cc.accent,
      blueLight: cc.accent + '18', blueMid: cc.accent + '30',
    })
  }
  const acc = { ...ACCENT_COLORS, ...EXTRA_ACCENTS }
  if (appearance.theme !== 'custom' && appearance.accentColor && acc[appearance.accentColor])
    Object.assign(base, acc[appearance.accentColor])
  return base
}

// ── Main App ───────────────────────────────────────────────────────────────────
// ── Side Project — floating quick-task panel ──────────────────────────────────
function SideProject({ onClose }) {
  const C = useTheme()
  const [input, setInput]       = useState('')
  const [messages, setMessages] = useState([])
  const [minimized, setMin]     = useState(false)
  const [streaming, setStreaming] = useState(false)
  const wsRef = useRef(null)
  const bottomRef = useRef(null)
  const bufRef = useRef('')

  useEffect(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws
    ws.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'stream_start') {
        bufRef.current = ''
        setStreaming(true)
        setMessages(p => [...p, { id: msg.msg_id + '_r', role:'assistant', content:'', streaming:true }])
      } else if (msg.type === 'chunk') {
        bufRef.current += msg.content
        setMessages(p => p.map(m => m.streaming ? { ...m, content: bufRef.current } : m))
      } else if (msg.type === 'stream_end') {
        setStreaming(false)
        setMessages(p => p.map(m => m.streaming ? { ...m, content: msg.display_content, streaming:false } : m))
      }
    }
    return () => ws.close()
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  const send = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || streaming) return
    const txt = input.trim()
    setMessages(p => [...p, { id: Date.now() + '_u', role:'user', content: txt }])
    setInput('')
    wsRef.current.send(JSON.stringify({ type:'message', content: txt, model:'ollama/llama3' }))
  }

  return (
    <div style={{
      position:'fixed', bottom:'80px', right:'18px', zIndex:800,
      width: minimized ? '220px' : '360px',
      maxHeight: minimized ? '48px' : '500px',
      background:C.white, borderRadius:'16px',
      border:`1.5px solid ${C.blue}40`,
      boxShadow:'0 8px 40px rgba(0,0,0,0.18)',
      display:'flex', flexDirection:'column',
      overflow:'hidden', transition:'all 0.3s cubic-bezier(0.34,1.3,0.64,1)',
      animation:'slideUp 0.3s ease',
    }}>
      {/* Header */}
      <div style={{
        display:'flex', alignItems:'center', padding:'10px 14px',
        background:`linear-gradient(135deg,${C.blue},${C.blueDark})`,
        color:'#fff', flexShrink:0, cursor:'pointer',
        borderRadius: minimized ? '14px' : '14px 14px 0 0',
      }} onClick={() => setMin(m => !m)}>
        <span style={{ fontSize:'15px', marginRight:'7px' }}>⚡</span>
        <span style={{ fontWeight:700, fontSize:'13px', flex:1 }}>Quick Task</span>
        <span style={{ fontSize:'11px', opacity:0.7, marginRight:'8px' }}>{minimized ? '▲' : '▼'}</span>
        <button onClick={e => { e.stopPropagation(); onClose() }}
          style={{ color:'rgba(255,255,255,0.7)', fontSize:'14px', padding:'2px 4px', borderRadius:'6px' }}>✕</button>
      </div>

      {!minimized && (
        <>
          {/* Messages */}
          <div style={{ flex:1, overflowY:'auto', padding:'12px', display:'flex', flexDirection:'column', gap:'8px', minHeight:'80px' }}>
            {messages.length === 0 && (
              <div style={{ color:C.textMuted, fontSize:'12px', textAlign:'center', marginTop:'16px', lineHeight:1.8 }}>
                ⚡ Quick task — no history saved.<br/>Draft, calculate, look something up.
              </div>
            )}
            {messages.map(m => (
              <div key={m.id} style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth:'85%', padding:'8px 11px', borderRadius: m.role === 'user' ? '14px 14px 4px 14px' : '4px 14px 14px 14px',
                background: m.role === 'user' ? C.blueLight : C.bgSecondary,
                border:`1px solid ${m.role === 'user' ? C.blueMid : C.border}`,
                fontSize:'13px', color:C.text, lineHeight:1.5,
              }}>{m.content || '…'}</div>
            ))}
            <div ref={bottomRef} />
          </div>
          {/* Input */}
          <div style={{ padding:'8px 10px', borderTop:`1px solid ${C.border}`, display:'flex', gap:'6px', flexShrink:0 }}>
            <input
              value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="Quick task…"
              style={{ flex:1, padding:'8px 10px', borderRadius:'10px', border:`1px solid ${input ? C.blue : C.border}`, fontSize:'13px', background:C.bg, color:C.text, outline:'none' }}
            />
            <button onClick={send} disabled={!input.trim() || streaming} style={{
              width:'34px', height:'34px', borderRadius:'9px', flexShrink:0,
              background: input.trim() && !streaming ? C.blue : C.border,
              color: input.trim() && !streaming ? '#fff' : C.textMuted,
              fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center',
            }}>↑</button>
          </div>
        </>
      )}
    </div>
  )
}

// ── Gmail Panel ───────────────────────────────────────────────────────────────
function GmailPanel({ onClose }) {
  const C = useTheme()
  const [status,  setStatus]  = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [tab,     setTab]     = useState('inbox')   // inbox | search | rules
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState(null)
  const [labeling, setLabeling] = useState(false)
  const [labelResult, setLabelResult] = useState(null)

  useEffect(() => {
    fetch(`${API}/api/gmail/status`).then(r=>r.json()).then(setStatus).catch(()=>{})
  }, [])

  const loadSummary = async () => {
    setLoading(true); setSummary(null)
    try { const d = await fetch(`${API}/api/gmail/summary?max_messages=20`).then(r=>r.json()); setSummary(d) }
    catch {}
    setLoading(false)
  }

  const doSearch = async () => {
    if (!query.trim()) return
    setLoading(true); setResults(null)
    try { const d = await fetch(`${API}/api/gmail/search?q=${encodeURIComponent(query)}&max_results=10`).then(r=>r.json()); setResults(d) }
    catch {}
    setLoading(false)
  }

  const doAutoLabel = async () => {
    setLabeling(true); setLabelResult(null)
    try { const d = await fetch(`${API}/api/gmail/autolabel`, {method:'POST'}).then(r=>r.json()); setLabelResult(d) }
    catch {}
    setLabeling(false)
  }

  const PANEL = {
    position:'fixed', top:0, right:0, bottom:0, width:'420px', maxWidth:'100vw',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    boxShadow:'-4px 0 32px rgba(0,0,0,0.12)',
    zIndex:800, display:'flex', flexDirection:'column',
    fontFamily:'system-ui,sans-serif',
  }

  return (
    <div style={PANEL}>
      {/* Header */}
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:'12px', background:`linear-gradient(135deg,${C.blue}18,${C.white})` }}>
        <span style={{ fontSize:'24px' }}>📧</span>
        <div style={{ flex:1 }}>
          <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>Gmail</div>
          {status?.configured
            ? <div style={{ fontSize:'12px', color:C.textMuted }}>{status.email} · {status.unread ?? '?'} unread</div>
            : <div style={{ fontSize:'12px', color:C.error }}>Not connected — run setup</div>}
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'20px', color:C.textMuted, cursor:'pointer', padding:'4px' }}>✕</button>
      </div>

      {!status?.configured && (
        <div style={{ padding:'20px', margin:'16px', background:'#FFFBEB', border:'1px solid #FDE68A', borderRadius:'10px', fontSize:'13px', color:'#92400E' }}>
          <strong>Setup Required</strong><br/>
          1. Go to <strong>console.cloud.google.com</strong><br/>
          2. Enable Gmail API + Drive API<br/>
          3. Create OAuth Desktop credentials → download as <code>google_credentials.json</code> into your REX folder<br/>
          4. Run: <code>python backend/rex_gmail.py --setup</code> in Terminal
        </div>
      )}

      {/* Tabs */}
      <div style={{ display:'flex', gap:'2px', padding:'8px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {['inbox','search','autolabel'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding:'6px 14px', borderRadius:'8px', border:'none', cursor:'pointer', fontSize:'13px', fontWeight: tab===t ? 700 : 400,
            background: tab===t ? C.blue : 'transparent', color: tab===t ? '#fff' : C.textMid,
          }}>{t === 'inbox' ? '📬 Inbox' : t === 'search' ? '🔍 Search' : '🏷 Auto-Label'}</button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex:1, overflowY:'auto', padding:'16px' }}>
        {tab === 'inbox' && (
          <>
            <button onClick={loadSummary} disabled={loading || !status?.configured} style={{
              width:'100%', padding:'10px', borderRadius:'8px', border:`1px solid ${C.border}`,
              background: C.bgSecondary, color:C.text, fontSize:'13px', cursor:'pointer', marginBottom:'12px',
            }}>{loading ? '⏳ Loading…' : '🔄 Refresh Inbox'}</button>
            {summary && (
              summary.ok
                ? <div>
                    <div style={{ fontSize:'13px', fontWeight:700, color:C.text, marginBottom:'8px' }}>{summary.count} unread message(s)</div>
                    {(summary.emails || []).map((e,i) => (
                      <div key={i} style={{ padding:'10px 12px', marginBottom:'6px', background:C.bgSecondary, borderRadius:'8px', borderLeft:`3px solid ${C.blue}` }}>
                        <div style={{ fontSize:'13px', fontWeight:600, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{e.subject}</div>
                        <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>{e.from}</div>
                        <div style={{ fontSize:'12px', color:C.textMid, marginTop:'4px' }}>{e.snippet?.slice(0,120)}…</div>
                      </div>
                    ))}
                  </div>
                : <div style={{ color:C.error, fontSize:'13px' }}>❌ {summary.error}</div>
            )}
          </>
        )}

        {tab === 'search' && (
          <>
            <div style={{ display:'flex', gap:'8px', marginBottom:'12px' }}>
              <input value={query} onChange={e=>setQuery(e.target.value)}
                onKeyDown={e => e.key==='Enter' && doSearch()}
                placeholder="e.g. from:gov.jm subject:authorization"
                style={{ flex:1, padding:'9px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px', background:C.bgSecondary, color:C.text }} />
              <button onClick={doSearch} disabled={loading || !status?.configured} style={{ padding:'9px 16px', borderRadius:'8px', background:C.blue, color:'#fff', border:'none', fontSize:'13px', cursor:'pointer' }}>
                {loading ? '…' : 'Search'}
              </button>
            </div>
            {results && (
              results.ok
                ? <div>
                    <div style={{ fontSize:'12px', color:C.textMuted, marginBottom:'8px' }}>{results.count} result(s) for "{query}"</div>
                    {(results.emails || []).map((e,i) => (
                      <div key={i} style={{ padding:'10px 12px', marginBottom:'6px', background:C.bgSecondary, borderRadius:'8px' }}>
                        <div style={{ fontSize:'13px', fontWeight:600, color:C.text }}>{e.subject}</div>
                        <div style={{ fontSize:'11px', color:C.textMuted }}>{e.from} · {e.date?.slice(0,16)}</div>
                        <div style={{ fontSize:'12px', color:C.textMid, marginTop:'4px' }}>{e.snippet?.slice(0,150)}…</div>
                      </div>
                    ))}
                  </div>
                : <div style={{ color:C.error, fontSize:'13px' }}>❌ {results.error}</div>
            )}
          </>
        )}

        {tab === 'autolabel' && (
          <>
            <div style={{ fontSize:'13px', color:C.textMid, marginBottom:'12px' }}>
              REX will scan your inbox and apply labels based on sender, keywords, and subject patterns.
              Labels created: <strong>REX/GOJ</strong>, <strong>REX/Authorizations</strong>, <strong>REX/Urgent</strong>, <strong>REX/Schedules</strong>
            </div>
            <button onClick={doAutoLabel} disabled={labeling || !status?.configured} style={{
              width:'100%', padding:'11px', borderRadius:'8px', border:'none',
              background:`linear-gradient(135deg,${C.blue},${C.blueDark})`, color:'#fff',
              fontSize:'14px', fontWeight:600, cursor:'pointer', marginBottom:'12px',
            }}>{labeling ? '⏳ Labeling…' : '🏷 Run Auto-Label Now'}</button>
            {labelResult && (
              labelResult.ok
                ? <div>
                    <div style={{ fontSize:'13px', fontWeight:600, color:C.success, marginBottom:'8px' }}>✅ {labelResult.summary}</div>
                    {(labelResult.actions || []).map((a,i) => (
                      <div key={i} style={{ padding:'8px 12px', marginBottom:'4px', background:C.bgSecondary, borderRadius:'6px', fontSize:'12px' }}>
                        <span style={{ color:C.blue }}>[{a.applied?.join(', ')}]</span> {a.subject}
                      </div>
                    ))}
                  </div>
                : <div style={{ color:C.error, fontSize:'13px' }}>❌ {labelResult.error}</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Upload Panel ──────────────────────────────────────────────────────────────
function UploadPanel({ onClose }) {
  const C = useTheme()
  const [tab,         setTab]       = useState('docs')  // 'docs' | 'training'
  const [files,       setFiles]     = useState([])
  const [uploading,   setUploading] = useState(false)
  const [uploadMsg,   setUploadMsg] = useState(null)
  const [driveFiles,  setDriveFiles]= useState([])
  const [driveLoading,setDriveLoad] = useState(false)
  const [syncing,     setSyncing]   = useState(false)
  const [syncMsg,     setSyncMsg]   = useState(null)
  const [dragOver,    setDragOver]  = useState(false)
  const fileInputRef = useRef(null)

  // Training tab state
  const [trainDragOver,  setTrainDragOver]  = useState(false)
  const [trainFile,      setTrainFile]      = useState(null)
  const [analysisType,   setAnalysisType]   = useState('compare')
  const [focusNote,      setFocusNote]      = useState('')
  const [trainUploading, setTrainUploading] = useState(false)
  const [trainMsg,       setTrainMsg]       = useState(null)
  const [trainQueue,     setTrainQueue]     = useState({ pending: [], completed: [] })
  const [trainQLoading,  setTrainQLoading]  = useState(false)
  const trainInputRef = useRef(null)

  const loadTrainQueue = async () => {
    setTrainQLoading(true)
    try { const d = await fetch(`${API}/api/training-queue`).then(r=>r.json()); setTrainQueue(d) } catch {}
    setTrainQLoading(false)
  }

  useEffect(() => { if (tab === 'training') loadTrainQueue() }, [tab])

  const doTrainUpload = async (fileObj) => {
    if (!fileObj) return
    setTrainFile(fileObj)
    setTrainUploading(true); setTrainMsg(null)
    const fd = new FormData()
    fd.append('file', fileObj)
    fd.append('analysis_type', analysisType)
    fd.append('focus', focusNote)
    try {
      const d = await fetch(`${API}/api/upload-training`, { method:'POST', body:fd }).then(r=>r.json())
      if (d.ok) {
        const extracted = d.text_extracted ? ' · Text extracted ✓' : ' · Binary file queued'
        setTrainMsg({ ok:true, text:`✅ Queued for analysis: ${d.filename}${extracted}` })
        setTrainFile(null); setFocusNote('')
        loadTrainQueue()
      } else {
        setTrainMsg({ ok:false, text:`❌ ${d.detail || 'Upload failed'}` })
      }
    } catch(e) {
      setTrainMsg({ ok:false, text:`❌ ${e.message}` })
    }
    setTrainUploading(false)
  }

  const loadFiles = async () => {
    try { const d = await fetch(`${API}/api/uploads`).then(r=>r.json()); setFiles(d.files || []) } catch {}
  }

  const loadDriveFiles = async () => {
    setDriveLoad(true)
    try { const d = await fetch(`${API}/api/drive/files`).then(r=>r.json()); setDriveFiles(d.files || []) } catch {}
    setDriveLoad(false)
  }

  useEffect(() => { loadFiles() }, [])

  const doUpload = async (fileList) => {
    if (!fileList?.length) return
    setUploading(true); setUploadMsg(null)
    const fd = new FormData()
    for (const f of fileList) fd.append('file', f)
    fd.append('sync_drive', 'true')
    try {
      const d = await fetch(`${API}/api/upload`, { method:'POST', body:fd }).then(r=>r.json())
      if (d.ok) {
        setUploadMsg({ ok:true, text:`✅ Uploaded: ${d.filename} (${(d.size/1024).toFixed(1)} KB)${d.drive?.ok ? ' + saved to Drive' : ''}` })
        loadFiles()
      } else {
        setUploadMsg({ ok:false, text:`❌ ${d.detail || 'Upload failed'}` })
      }
    } catch (e) {
      setUploadMsg({ ok:false, text:`❌ ${e.message}` })
    }
    setUploading(false)
  }

  const doSync = async () => {
    setSyncing(true); setSyncMsg(null)
    try { const d = await fetch(`${API}/api/drive/sync`,{method:'POST'}).then(r=>r.json()); setSyncMsg(d) } catch {}
    setSyncing(false)
  }

  const deleteFile = async (name) => {
    try {
      await fetch(`${API}/api/uploads/${encodeURIComponent(name)}`, { method:'DELETE' })
      loadFiles()
    } catch {}
  }

  const fmtSize = bytes => bytes < 1024 ? `${bytes}B` : bytes < 1048576 ? `${(bytes/1024).toFixed(1)}KB` : `${(bytes/1048576).toFixed(1)}MB`
  const fmtDate = ts => new Date(ts*1000).toLocaleDateString()

  const PANEL = {
    position:'fixed', top:0, right:0, bottom:0, width:'440px', maxWidth:'100vw',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    boxShadow:'-4px 0 32px rgba(0,0,0,0.12)',
    zIndex:800, display:'flex', flexDirection:'column',
  }

  const ANALYSIS_LABELS = {
    compare:   { icon:'⚖️', label:'Compare & Check',  desc:'Double-check employee files — discrepancies, red flags, verdict' },
    mistakes:  { icon:'🔍', label:'Find Mistakes',    desc:'Errors, inconsistencies, problems — with severity rating' },
    learn:     { icon:'📚', label:'Learn Patterns',   desc:'Key procedures and best practices to extract and remember' },
    summarize: { icon:'📋', label:'Quick Summary',    desc:'Overview, key points, flags, and action items' },
    full:      { icon:'🧠', label:'Full Analysis',    desc:'Everything: mistakes, patterns, actions, recommendations' },
  }

  return (
    <div style={PANEL}>
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:'12px', background:`linear-gradient(135deg,${C.blue}18,${C.white})` }}>
        <span style={{ fontSize:'24px' }}>{tab === 'training' ? '🧠' : '📁'}</span>
        <div style={{ flex:1 }}>
          <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>{tab === 'training' ? 'REX & Rexxie Training' : 'Documents & Uploads'}</div>
          <div style={{ fontSize:'12px', color:C.textMuted }}>{tab === 'training' ? 'Chairman private · Analysis sent via Rexxie' : `${files.length} file(s) stored locally`}</div>
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'20px', color:C.textMuted, cursor:'pointer' }}>✕</button>
      </div>

      {/* Tab switcher */}
      <div style={{ display:'flex', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {[{id:'docs',label:'📁 Documents'},{id:'training',label:'🧠 Training'}].map(t => (
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            flex:1, padding:'11px 8px', border:'none', cursor:'pointer', fontSize:'13px', fontWeight: tab===t.id ? 700 : 400,
            borderBottom: tab===t.id ? `3px solid ${t.id==='training'?'#6B3FA0':C.blue}` : '3px solid transparent',
            background:'transparent',
            color: tab===t.id ? (t.id==='training'?'#6B3FA0':C.blue) : C.textMuted,
            transition:'all 0.15s',
          }}>{t.label}</button>
        ))}
      </div>

      {/* ── DOCUMENTS TAB ── */}
      {tab === 'docs' && (
        <div style={{ flex:1, overflowY:'auto', padding:'16px' }}>
          {/* Drop zone */}
          <div
            onDragOver={e=>{e.preventDefault();setDragOver(true)}}
            onDragLeave={()=>setDragOver(false)}
            onDrop={e=>{e.preventDefault();setDragOver(false);doUpload(Array.from(e.dataTransfer.files))}}
            onClick={()=>fileInputRef.current?.click()}
            style={{
              border:`2px dashed ${dragOver ? C.blue : C.border}`, borderRadius:'12px',
              padding:'28px 20px', textAlign:'center', cursor:'pointer', marginBottom:'16px',
              background: dragOver ? `${C.blue}10` : C.bgSecondary, transition:'all 0.2s',
            }}
          >
            <div style={{ fontSize:'32px', marginBottom:'8px' }}>{uploading ? '⏳' : '📤'}</div>
            <div style={{ fontSize:'14px', fontWeight:600, color:C.text }}>{uploading ? 'Uploading…' : 'Drop files here or click to browse'}</div>
            <div style={{ fontSize:'12px', color:C.textMuted, marginTop:'4px' }}>Authorizations, schedules, docs — auto-synced to Drive</div>
          </div>
          <input ref={fileInputRef} type="file" multiple onChange={e=>doUpload(Array.from(e.target.files))} style={{display:'none'}} />

          {uploadMsg && (
            <div style={{ padding:'10px 14px', borderRadius:'8px', marginBottom:'12px', fontSize:'13px',
              background: uploadMsg.ok ? '#ECFDF5' : '#FEF2F2', color: uploadMsg.ok ? C.success : C.error }}>
              {uploadMsg.text}
            </div>
          )}

          <div style={{ display:'flex', gap:'8px', marginBottom:'16px' }}>
            <button onClick={doSync} disabled={syncing} style={{ flex:1, padding:'9px', borderRadius:'8px', border:`1px solid ${C.border}`, background:C.bgSecondary, color:C.text, fontSize:'13px', cursor:'pointer' }}>{syncing ? '⏳ Syncing…' : '☁️ Sync to Drive'}</button>
            <button onClick={()=>{loadDriveFiles()}} disabled={driveLoading} style={{ flex:1, padding:'9px', borderRadius:'8px', border:`1px solid ${C.border}`, background:C.bgSecondary, color:C.text, fontSize:'13px', cursor:'pointer' }}>{driveLoading ? '⏳' : '📂 View Drive Files'}</button>
          </div>
          {syncMsg && <div style={{ fontSize:'12px', color:syncMsg.ok ? C.success : C.error, marginBottom:'12px' }}>{syncMsg.summary || syncMsg.error}</div>}

          <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.6px', textTransform:'uppercase', marginBottom:'8px' }}>Local Files ({files.length})</div>
          {files.length === 0 && <div style={{ fontSize:'13px', color:C.textMuted, padding:'12px 0' }}>No files yet.</div>}
          {files.map((f,i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', padding:'9px 12px', marginBottom:'4px', background:C.bgSecondary, borderRadius:'8px', gap:'10px' }}>
              <span style={{ fontSize:'18px' }}>📄</span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:'13px', fontWeight:600, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{f.name}</div>
                <div style={{ fontSize:'11px', color:C.textMuted }}>{fmtSize(f.size)} · {fmtDate(f.modified)}</div>
              </div>
              <a href={`${API}${f.url}`} download={f.name} style={{ fontSize:'13px', color:C.blue, textDecoration:'none' }}>⬇</a>
              <button onClick={()=>deleteFile(f.name)} style={{ background:'none', border:'none', fontSize:'14px', color:C.error, cursor:'pointer', padding:'2px 4px' }}>✕</button>
            </div>
          ))}

          {driveFiles.length > 0 && (
            <>
              <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, letterSpacing:'0.6px', textTransform:'uppercase', margin:'16px 0 8px' }}>☁️ Google Drive — REX Documents</div>
              {driveFiles.map((f,i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', padding:'9px 12px', marginBottom:'4px', background:C.bgSecondary, borderRadius:'8px', gap:'10px' }}>
                  <span style={{ fontSize:'18px' }}>☁️</span>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize:'13px', fontWeight:600, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{f.name}</div>
                  </div>
                  {f.webViewLink && <a href={f.webViewLink} target="_blank" rel="noopener noreferrer" style={{ fontSize:'13px', color:C.blue, textDecoration:'none' }}>Open ↗</a>}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* ── TRAINING TAB ── */}
      {tab === 'training' && (
        <div style={{ flex:1, overflowY:'auto', padding:'16px' }}>

          {/* Info banner */}
          <div style={{ background:'#F5F0FF', border:'1px solid #D4C5F9', borderRadius:'10px', padding:'11px 14px', marginBottom:'16px' }}>
            <div style={{ fontWeight:700, fontSize:'13px', color:'#6B3FA0', marginBottom:'4px' }}>🐢 Chairman Private Training</div>
            <div style={{ fontSize:'12px', color:'#5A3D8A', lineHeight:'1.5' }}>
              Drop documents here — schedules, reports, authorizations, notes, anything you want REX and Rexxie to analyze. Results come only to you via Rexxie's Telegram.
            </div>
          </div>

          {/* Analysis type selector */}
          <div style={{ marginBottom:'14px' }}>
            <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'8px' }}>Analysis Type</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'6px' }}>
              {/* Compare & Check spans full width as the primary/default option */}
              {Object.entries(ANALYSIS_LABELS).map(([key, info]) => (
                <button key={key} onClick={()=>setAnalysisType(key)} style={{
                  padding:'10px 10px', borderRadius:'9px', border:`2px solid ${analysisType===key?'#6B3FA0':C.border}`,
                  background: analysisType===key ? '#F5F0FF' : C.bgSecondary,
                  cursor:'pointer', textAlign:'left', transition:'all 0.15s',
                }}>
                  <div style={{ fontSize:'15px', marginBottom:'2px' }}>{info.icon}</div>
                  <div style={{ fontSize:'12px', fontWeight:700, color: analysisType===key?'#6B3FA0':C.text }}>{info.label}</div>
                  <div style={{ fontSize:'10px', color:C.textMuted, lineHeight:'1.3', marginTop:'2px' }}>{info.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Optional focus note */}
          <div style={{ marginBottom:'14px' }}>
            <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'6px' }}>Focus (optional)</div>
            <textarea
              value={focusNote}
              onChange={e=>setFocusNote(e.target.value)}
              placeholder="e.g. 'Look specifically at billing codes' or 'Are driver assignments correct?'"
              rows={2}
              style={{
                width:'100%', boxSizing:'border-box', padding:'9px 12px', borderRadius:'8px',
                border:`1px solid ${C.border}`, fontSize:'13px', color:C.text,
                background:C.bgSecondary, resize:'vertical', outline:'none',
                fontFamily:'inherit',
              }}
            />
          </div>

          {/* Training drop zone */}
          <div
            onDragOver={e=>{e.preventDefault();setTrainDragOver(true)}}
            onDragLeave={()=>setTrainDragOver(false)}
            onDrop={e=>{
              e.preventDefault(); setTrainDragOver(false)
              const f = e.dataTransfer.files[0]
              if (f) doTrainUpload(f)
            }}
            onClick={()=>trainInputRef.current?.click()}
            style={{
              border:`2px dashed ${trainDragOver ? '#6B3FA0' : C.border}`, borderRadius:'12px',
              padding:'32px 20px', textAlign:'center', cursor:'pointer', marginBottom:'14px',
              background: trainDragOver ? '#F5F0FF' : trainUploading ? '#F5F0FF' : C.bgSecondary,
              transition:'all 0.2s',
            }}
          >
            <div style={{ fontSize:'36px', marginBottom:'8px' }}>{trainUploading ? '⏳' : trainFile ? '📄' : '🧠'}</div>
            <div style={{ fontSize:'14px', fontWeight:700, color: trainDragOver?'#6B3FA0':C.text }}>
              {trainUploading ? 'Analyzing…' : trainFile ? trainFile.name : 'Drop your document here'}
            </div>
            <div style={{ fontSize:'12px', color:C.textMuted, marginTop:'5px' }}>
              PDF, DOCX, TXT, XLSX, JPG — any document you want REX to examine
            </div>
            <div style={{ fontSize:'11px', color:'#6B3FA0', marginTop:'8px', fontWeight:600 }}>
              {ANALYSIS_LABELS[analysisType].icon} {ANALYSIS_LABELS[analysisType].label} selected
            </div>
          </div>
          <input ref={trainInputRef} type="file" accept=".pdf,.docx,.doc,.txt,.xlsx,.csv,.jpg,.jpeg,.png" onChange={e=>{const f=e.target.files[0]; if(f)doTrainUpload(f)}} style={{display:'none'}} />

          {trainMsg && (
            <div style={{ padding:'10px 14px', borderRadius:'8px', marginBottom:'14px', fontSize:'13px',
              background: trainMsg.ok ? '#ECFDF5' : '#FEF2F2', color: trainMsg.ok ? '#1A7F37' : C.error, lineHeight:'1.5' }}>
              {trainMsg.text}
              {trainMsg.ok && <div style={{ fontSize:'11px', marginTop:'4px', color:'#1A7F37', opacity:0.8 }}>Rexxie will send you the analysis when it's ready — usually within the next AI training window.</div>}
            </div>
          )}

          {/* Queue status */}
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'8px' }}>
            <div style={{ fontSize:'12px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px' }}>
              Training Queue ({trainQueue.pending?.length || 0} pending)
            </div>
            <button onClick={loadTrainQueue} style={{ fontSize:'12px', color:'#6B3FA0', background:'none', border:'none', cursor:'pointer', padding:'2px 6px' }}>↻ Refresh</button>
          </div>

          {trainQLoading && <div style={{ fontSize:'12px', color:C.textMuted, padding:'8px 0' }}>Loading…</div>}

          {!trainQLoading && trainQueue.pending?.length === 0 && trainQueue.completed?.length === 0 && (
            <div style={{ fontSize:'13px', color:C.textMuted, padding:'8px 0' }}>No training documents uploaded yet.</div>
          )}

          {trainQueue.pending?.map((item, i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', padding:'9px 12px', marginBottom:'4px', background:'#FFF8E0', border:'1px solid #F6E05E', borderRadius:'8px', gap:'10px' }}>
              <span style={{ fontSize:'16px' }}>⏳</span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:'12px', fontWeight:600, color:'#744210', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{item.filename}</div>
                <div style={{ fontSize:'10px', color:'#A0522D' }}>{ANALYSIS_LABELS[item.analysis_type]?.label || item.analysis_type} · Queued {item.date}</div>
              </div>
              <span style={{ fontSize:'10px', background:'#F6E05E', color:'#744210', borderRadius:'5px', padding:'2px 6px', fontWeight:700, flexShrink:0 }}>QUEUED</span>
            </div>
          ))}

          {trainQueue.completed?.length > 0 && (
            <div style={{ marginTop:'8px' }}>
              <div style={{ fontSize:'11px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'6px' }}>Completed</div>
              {trainQueue.completed.map((item, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', padding:'9px 12px', marginBottom:'4px', background:'#ECFDF5', border:'1px solid #9AE6B4', borderRadius:'8px', gap:'10px' }}>
                  <span style={{ fontSize:'16px' }}>✅</span>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize:'12px', fontWeight:600, color:'#1A5236', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{item.filename}</div>
                    <div style={{ fontSize:'10px', color:'#276749' }}>{ANALYSIS_LABELS[item.analysis_type]?.label || item.analysis_type} · {item.date}{item.has_report ? ' · Report available' : ''}</div>
                  </div>
                  <span style={{ fontSize:'10px', background:'#9AE6B4', color:'#1A5236', borderRadius:'5px', padding:'2px 6px', fontWeight:700, flexShrink:0 }}>DONE</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Calendar Panel ────────────────────────────────────────────────────────────
function CalendarPanel({ onClose, pendingPdfs = [] }) {
  const C = useTheme()
  const today    = new Date()
  const todayISO = today.toISOString().slice(0,10)

  const [tab,          setTab]          = useState('day')   // 'day' | 'month'
  const [selectedDate, setSelectedDate] = useState(todayISO)
  const [dayData,      setDayData]      = useState(null)
  const [monthData,    setMonthData]    = useState(null)
  const [loading,      setLoading]      = useState(false)
  const [monthLoading, setMonthLoading] = useState(false)

  const selD       = new Date(selectedDate + 'T00:00:00')
  const year       = selD.getFullYear()
  const month      = selD.getMonth()
  const firstDay   = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month+1, 0).getDate()
  const monthName  = selD.toLocaleString('default', { month:'long', year:'numeric' })

  const prevMonth = () => {
    const d = new Date(year, month-1, 1)
    setSelectedDate(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`)
  }
  const nextMonth = () => {
    const d = new Date(year, month+1, 1)
    setSelectedDate(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`)
  }
  const selectDay = (day) => {
    const iso = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`
    setSelectedDate(iso)
    setTab('day')
  }

  // Fetch day detail from /api/day-summary
  useEffect(() => {
    if (tab !== 'day') return
    setLoading(true)
    setDayData(null)
    fetch(`${API}/api/day-summary?date=${selectedDate}`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(d => { setDayData(d); setLoading(false) })
  }, [selectedDate, tab])

  // Fetch month overview from /api/month-summary
  useEffect(() => {
    if (tab !== 'month') return
    setMonthLoading(true)
    fetch(`${API}/api/month-summary?year=${year}&month=${month+1}`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(d => { setMonthData(d); setMonthLoading(false) })
  }, [tab, year, month])

  const isToday    = (d) => `${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}` === todayISO
  const isSelected = (d) => `${year}-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}` === selectedDate

  const DOW_LABELS   = ['Su','Mo','Tu','We','Th','Fr','Sa']
  // Sun=0,Mon=1,Tue=2,Wed=3,Thu=4,Fri=5,Sat=6
  const AI_DOW_JS = { 2:'🟡', 3:'🟢', 5:'🔵' } // Tue=Grok,Wed=ChatGPT,Fri=Gemini (JS getDay)
  // NOTE: backend uses Python weekday (Mon=0), JS uses Sun=0
  const AI_COLORS = { Grok:'#c9a84c', ChatGPT:'#10A37F', Gemini:'#4285F4' }

  const panelStyle = {
    position:'fixed', top:0, right:0, width:'380px', height:'100vh',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    display:'flex', flexDirection:'column', zIndex:500,
    boxShadow:'-4px 0 24px rgba(0,0,0,0.10)',
  }

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ padding:'14px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center', flexShrink:0 }}>
        <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>📅 Schedule</div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'20px', cursor:'pointer', color:C.textMuted }}>×</button>
      </div>

      {/* Tab switcher */}
      <div style={{ display:'flex', gap:'4px', padding:'8px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {[{id:'day',label:'Day View'},{id:'month',label:'Month View'}].map(t => (
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            flex:1, padding:'6px', borderRadius:'8px', border:'none', cursor:'pointer', fontSize:'13px',
            background: tab===t.id ? C.blue : C.bgSecondary,
            color: tab===t.id ? '#fff' : C.textMid, fontWeight: tab===t.id ? 700 : 400,
          }}>{t.label}</button>
        ))}
      </div>

      {/* PDF Inbox — pending extraction prompts */}
      {pendingPdfs.length > 0 && (
        <div style={{ background:'#FFF5F5', borderBottom:`2px solid #FC8181`, padding:'10px 16px', flexShrink:0 }}>
          <div style={{ fontWeight:700, fontSize:'12px', color:'#C53030', marginBottom:'6px' }}>
            📥 {pendingPdfs.length} PDF Email{pendingPdfs.length > 1 ? 's' : ''} — Reply to Rexxie to Extract
          </div>
          {pendingPdfs.slice(0,3).map((p,i) => (
            <div key={i} style={{ fontSize:'11px', color:'#742A2A', marginBottom:'3px', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              📄 {p.subject} <span style={{ color:'#A0AEC0' }}>· {(p.pdf_names||[]).join(', ')}</span>
            </div>
          ))}
          {pendingPdfs.length > 3 && (
            <div style={{ fontSize:'11px', color:'#C53030', marginTop:'2px' }}>+{pendingPdfs.length - 3} more — check 9 PM report</div>
          )}
        </div>
      )}

      {/* Month nav — shown in both tabs */}
      <div style={{ padding:'10px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
        <button onClick={prevMonth} style={{ background:'none', border:`1px solid ${C.border}`, borderRadius:'8px', padding:'4px 12px', cursor:'pointer', color:C.text, fontSize:'15px' }}>‹</button>
        <span style={{ fontWeight:600, fontSize:'14px', color:C.text }}>{monthName}</span>
        <button onClick={nextMonth} style={{ background:'none', border:`1px solid ${C.border}`, borderRadius:'8px', padding:'4px 12px', cursor:'pointer', color:C.text, fontSize:'15px' }}>›</button>
      </div>

      {/* ── DAY VIEW ── */}
      {tab === 'day' && (
        <>
          {/* Mini calendar grid */}
          <div style={{ padding:'10px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:'2px', textAlign:'center', marginBottom:'4px' }}>
              {DOW_LABELS.map(d => <div key={d} style={{ fontSize:'10px', color:C.textMuted, fontWeight:600 }}>{d}</div>)}
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:'2px', textAlign:'center' }}>
              {Array.from({length: firstDay}).map((_,i) => <div key={`e${i}`} />)}
              {Array.from({length: daysInMonth}).map((_,i) => {
                const d = i+1
                const dow = new Date(year, month, d).getDay()
                const sel = isSelected(d), tod = isToday(d)
                const hasTrain = !!AI_DOW_JS[dow]
                return (
                  <button key={d} onClick={() => selectDay(d)} style={{
                    width:'100%', aspectRatio:'1', border:'none', borderRadius:'6px', cursor:'pointer',
                    fontSize:'11px', fontWeight: sel||tod ? 700 : 400,
                    background: sel ? C.blue : tod ? C.blueLight : 'transparent',
                    color: sel ? '#fff' : tod ? C.blue : C.text,
                    position:'relative', display:'flex', alignItems:'center', justifyContent:'center',
                  }}>
                    {d}
                    {hasTrain && <span style={{ position:'absolute', bottom:'1px', left:'50%', transform:'translateX(-50%)', width:'3px', height:'3px', borderRadius:'50%', background: sel?'rgba(255,255,255,0.8)':C.blue }} />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Day detail */}
          <div style={{ flex:1, overflowY:'auto', padding:'14px 16px' }}>
            {loading ? (
              <div style={{ textAlign:'center', color:C.textMuted, marginTop:'32px' }}>Loading…</div>
            ) : dayData ? (
              <>
                <div style={{ fontWeight:700, fontSize:'15px', color:C.text, marginBottom:'14px' }}>
                  {new Date(selectedDate+'T00:00:00').toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'})}
                  {dayData.is_today && <span style={{ marginLeft:'8px', fontSize:'11px', background:C.blue, color:'#fff', borderRadius:'6px', padding:'2px 7px' }}>TODAY</span>}
                </div>

                {/* AI Training */}
                {dayData.ai_training && (
                  <div style={{ background:C.blueLight, border:`1px solid ${C.blueMid}`, borderRadius:'10px', padding:'11px 13px', marginBottom:'10px' }}>
                    <div style={{ fontSize:'11px', fontWeight:700, color:C.blue, textTransform:'uppercase', letterSpacing:'0.5px' }}>AI Training</div>
                    <div style={{ fontSize:'13px', color:C.text, marginTop:'5px', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <span>📚 {dayData.ai_training} session</span>
                      {dayData.training_done
                        ? <span style={{ fontSize:'11px', background:'#E6F4EA', color:'#1A7F37', borderRadius:'6px', padding:'2px 8px', fontWeight:700 }}>✅ Done</span>
                        : <span style={{ fontSize:'11px', background:'#FFF8E0', color:'#8a6020', borderRadius:'6px', padding:'2px 8px', fontWeight:700 }}>Queued</span>
                      }
                    </div>
                    {dayData.training_file && <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'3px' }}>→ {dayData.training_file}</div>}
                  </div>
                )}

                {/* Evening report */}
                {dayData.evening_log && (
                  <div style={{ background:C.bgSecondary, borderRadius:'10px', padding:'11px 13px', marginBottom:'10px' }}>
                    <div style={{ fontSize:'11px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'5px' }}>9 PM Report</div>
                    <pre style={{ fontSize:'11px', color:C.text, whiteSpace:'pre-wrap', wordBreak:'break-word', margin:0, fontFamily:'inherit' }}>{dayData.evening_log}</pre>
                  </div>
                )}

                {/* Documents */}
                {dayData.documents?.length > 0 && (
                  <div style={{ background:C.bgSecondary, borderRadius:'10px', padding:'11px 13px', marginBottom:'10px' }}>
                    <div style={{ fontSize:'11px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'5px' }}>Documents</div>
                    {dayData.documents.map(f => (
                      <div key={f.name} style={{ fontSize:'12px', color:C.text, marginBottom:'2px' }}>📄 {f.name}</div>
                    ))}
                  </div>
                )}

                {/* Personal Events (Chairman only) */}
                {dayData.personal_events?.length > 0 && (
                  <div style={{ background:'#F5F0FF', border:'1px solid #D4C5F9', borderRadius:'10px', padding:'11px 13px', marginBottom:'10px' }}>
                    <div style={{ fontSize:'11px', fontWeight:700, color:'#6B3FA0', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:'6px' }}>🐢 Personal Schedule</div>
                    {dayData.personal_events.map(ev => {
                      const timeLabel = ev.event_time ? (() => {
                        try {
                          const [h,m] = ev.event_time.split(':').map(Number)
                          const s = h < 12 ? 'AM' : 'PM'
                          const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
                          return `${h12}:${String(m).padStart(2,'0')} ${s}`
                        } catch { return ev.event_time }
                      })() : null
                      return (
                        <div key={ev.id} style={{ marginBottom:'8px', paddingBottom:'8px', borderBottom:'1px solid #E8DFF9' }}>
                          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
                            <div style={{ fontWeight:600, fontSize:'13px', color:'#3D2066' }}>{ev.title}</div>
                            {timeLabel && <div style={{ fontSize:'11px', color:'#6B3FA0', flexShrink:0, marginLeft:'6px', background:'#EDE6FF', borderRadius:'5px', padding:'1px 6px' }}>{timeLabel}</div>}
                          </div>
                          {ev.notes && <div style={{ fontSize:'11px', color:'#5A3D8A', marginTop:'3px' }}>{ev.notes}</div>}
                          {ev.reminder_at && !ev.reminded && <div style={{ fontSize:'10px', color:'#8B6FC0', marginTop:'3px' }}>🔔 Reminder set</div>}
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Day type badge */}
                <div style={{ background: dayData.is_weekend ? C.bgSecondary : C.blueLight, borderRadius:'10px', padding:'11px 13px' }}>
                  <div style={{ fontSize:'11px', fontWeight:700, color: dayData.is_weekend ? C.textMuted : C.blue, textTransform:'uppercase', letterSpacing:'0.5px' }}>
                    {dayData.is_weekend ? 'Weekend' : 'Weekday'}
                  </div>
                  <div style={{ fontSize:'12px', color:C.textMid, marginTop:'4px' }}>
                    {dayData.day_of_week}
                    {dayData.day_of_week === 'Sunday' && ' · AI prompts auto-queued tonight'}
                    {!dayData.ai_training && !dayData.is_weekend && ' · No AI training today'}
                  </div>
                  {!dayData.evening_log && !dayData.personal_events?.length && (
                    <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'6px' }}>
                      Activity schedules will populate here once uploaded.
                    </div>
                  )}
                </div>
              </>
            ) : null}
          </div>
        </>
      )}

      {/* ── MONTH VIEW ── */}
      {tab === 'month' && (
        <div style={{ flex:1, overflowY:'auto' }}>
          {monthLoading ? (
            <div style={{ textAlign:'center', color:C.textMuted, marginTop:'40px' }}>Loading month…</div>
          ) : monthData ? (
            <div style={{ padding:'8px 0' }}>
              {/* Legend */}
              <div style={{ display:'flex', gap:'12px', padding:'8px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0, flexWrap:'wrap' }}>
                <span style={{ fontSize:'11px', color:C.textMuted }}>🟡 Grok &nbsp; 🟢 ChatGPT &nbsp; 🔵 Gemini &nbsp; ✅ Done</span>
              </div>
              {monthData.days.map(d => {
                const aiColor = d.ai === 'Grok' ? '#c9a84c' : d.ai === 'ChatGPT' ? '#10A37F' : d.ai === 'Gemini' ? '#4285F4' : null
                const aiDot   = d.ai === 'Grok' ? '🟡' : d.ai === 'ChatGPT' ? '🟢' : d.ai === 'Gemini' ? '🔵' : null
                return (
                  <button key={d.date} onClick={() => selectDay(d.day)} style={{
                    display:'flex', alignItems:'center', gap:'10px',
                    width:'100%', padding:'9px 16px', border:'none',
                    borderBottom:`1px solid ${C.border}`,
                    background: d.is_today ? C.blueLight : d.date === selectedDate ? C.bgSecondary : 'transparent',
                    cursor:'pointer', textAlign:'left',
                  }}>
                    {/* Date number */}
                    <div style={{
                      width:'32px', height:'32px', borderRadius:'8px', flexShrink:0,
                      background: d.is_today ? C.blue : d.is_weekend ? C.bgSecondary : 'transparent',
                      border: d.is_today ? 'none' : `1px solid ${d.is_weekend ? C.border : 'transparent'}`,
                      display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center',
                    }}>
                      <span style={{ fontSize:'13px', fontWeight: d.is_today ? 700 : 500, color: d.is_today ? '#fff' : d.is_past ? C.textMuted : C.text, lineHeight:1 }}>{d.day}</span>
                      <span style={{ fontSize:'9px', color: d.is_today ? 'rgba(255,255,255,0.8)' : C.textMuted, lineHeight:1 }}>{d.dow_name.slice(0,3)}</span>
                    </div>
                    {/* Events for the day */}
                    <div style={{ flex:1, minWidth:0 }}>
                      {d.ai && (
                        <div style={{ display:'flex', alignItems:'center', gap:'5px' }}>
                          <span style={{ fontSize:'12px' }}>{aiDot}</span>
                          <span style={{ fontSize:'12px', color: aiColor, fontWeight:600 }}>{d.ai} training</span>
                          {d.ai_done && <span style={{ fontSize:'11px', color:'#1A7F37' }}>✅</span>}
                        </div>
                      )}
                      {d.dow_name === 'Sunday' && <div style={{ fontSize:'11px', color:C.blue }}>🔄 Sunday prep</div>}
                      {d.is_weekend && !d.ai && <div style={{ fontSize:'11px', color:C.textMuted }}>Weekend</div>}
                      {!d.ai && !d.is_weekend && <div style={{ fontSize:'11px', color:C.textMuted }}>Operational day</div>}
                    </div>
                    {d.is_today && <span style={{ fontSize:'10px', background:C.blue, color:'#fff', borderRadius:'6px', padding:'2px 6px', flexShrink:0 }}>TODAY</span>}
                  </button>
                )
              })}
            </div>
          ) : (
            <div style={{ textAlign:'center', color:C.textMuted, marginTop:'40px' }}>Unable to load month data</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Employee Permissions Panel ────────────────────────────────────────────────
// Chairman-only: grant or revoke panel access for each employee.
const ALL_PANELS = [
  { id: 'attendance',  label: '📋 Client Attendance',   desc: 'View daily sign-in & client roster' },
  { id: 'calendar',    label: '📅 Calendar',             desc: 'View chairman events & reminders' },
  { id: 'documents',   label: '📁 Documents & Upload',   desc: 'Upload and browse GOJ files' },
  { id: 'gmail',       label: '📧 Gmail Panel',          desc: 'View inbox and labels' },
  { id: 'telegram',    label: '📡 Telegram / GOJ Feed',  desc: 'View GOJ Telegram channel feed' },
  { id: 'edi',         label: '💊 EDI Billing',          desc: 'Upload and view 837/835 EDI files' },
  { id: 'upload',      label: '📤 Upload Panel',         desc: 'Upload documents to the system' },
]

function EmployeePermissionsPanel({ onClose, authToken = '' }) {
  const C = useTheme()
  const [users,   setUsers]   = useState([])
  const [loading, setLoading] = useState(true)
  const [saving,  setSaving]  = useState(null)   // user_id being saved
  const [saved,   setSaved]   = useState(null)   // user_id just saved
  const [perms,   setPerms]   = useState({})     // { user_id: Set<panel_id> }

  const headers = { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' }

  useEffect(() => {
    fetch(`${API}/api/auth/users`, { headers })
      .then(r => r.ok ? r.json() : { users: [] })
      .catch(() => ({ users: [] }))
      .then(d => {
        const staff = (d.users || []).filter(u => u.role !== 'chairman')
        setUsers(staff)
        const p = {}
        staff.forEach(u => { p[u.id] = new Set(u.panel_permissions || []) })
        setPerms(p)
        setLoading(false)
      })
  }, [authToken])

  const togglePerm = (userId, panel) => {
    setPerms(prev => {
      const s = new Set(prev[userId] || [])
      s.has(panel) ? s.delete(panel) : s.add(panel)
      return { ...prev, [userId]: s }
    })
  }

  const saveUser = async (userId) => {
    setSaving(userId)
    const permList = Array.from(perms[userId] || [])
    await fetch(`${API}/api/auth/users/${userId}/permissions`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ permissions: permList })
    }).catch(() => {})
    setSaving(null)
    setSaved(userId)
    setTimeout(() => setSaved(s => s === userId ? null : s), 2000)
  }

  return (
    <div style={{
      position:'fixed', top:0, right:0, bottom:0, width:'min(560px,100vw)',
      background: C.white, borderLeft:`1px solid ${C.border}`,
      zIndex: 500, display:'flex', flexDirection:'column',
      boxShadow:'-4px 0 24px rgba(0,0,0,0.08)',
    }}>
      {/* Header */}
      <div style={{
        padding:'16px 20px', borderBottom:`1px solid ${C.border}`,
        display:'flex', alignItems:'center', gap:'12px', flexShrink:0,
        background:'linear-gradient(135deg,#6B46C1,#553C9A)',
      }}>
        <span style={{ fontSize:'22px' }}>🔑</span>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:'16px', fontWeight:700, color:'#fff' }}>Manage Employee Access</div>
          <div style={{ fontSize:'12px', color:'rgba(255,255,255,0.75)' }}>Grant or revoke dashboard panel access for each employee</div>
        </div>
        <button onClick={onClose} style={{
          background:'rgba(255,255,255,0.15)', border:'none', color:'#fff',
          borderRadius:'50%', width:'30px', height:'30px',
          display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer',
          fontSize:'14px',
        }}>✕</button>
      </div>

      {/* Restricted notice */}
      <div style={{ padding:'10px 20px', background:'#FFF8E1', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        <span style={{ fontSize:'12px', color:'#8A6020' }}>
          🔒 <b>Staff Compliance</b> is permanently restricted to Chairman and Director — it cannot be granted to employees.
        </span>
      </div>

      {/* Body */}
      <div style={{ flex:1, overflowY:'auto', padding:'16px 20px' }}>
        {loading && <div style={{ textAlign:'center', padding:'40px', color:C.textMuted }}>Loading employees…</div>}
        {!loading && users.length === 0 && (
          <div style={{ textAlign:'center', padding:'40px', color:C.textMuted }}>
            No staff accounts yet. Create accounts from the Settings panel.
          </div>
        )}
        {!loading && users.map(user => (
          <div key={user.id} style={{
            background: C.bgSecondary, borderRadius:'10px', padding:'14px 16px',
            marginBottom:'14px', border:`1px solid ${C.border}`,
          }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'10px' }}>
              <div>
                <span style={{ fontWeight:700, color:C.text, fontSize:'14px' }}>
                  {user.first_name} {user.last_name}
                </span>
                <span style={{ marginLeft:'8px', fontSize:'11px', color:C.textMuted }}>@{user.username}</span>
                <span style={{
                  marginLeft:'8px', padding:'2px 6px', borderRadius:'4px',
                  fontSize:'10px', fontWeight:600,
                  background: user.role === 'admin' ? '#EBF2FF' : '#F0FFF4',
                  color: user.role === 'admin' ? '#1045B8' : '#276749',
                }}>{user.role}</span>
              </div>
              <button
                onClick={() => saveUser(user.id)}
                disabled={saving === user.id}
                style={{
                  padding:'5px 12px', borderRadius:'6px', fontSize:'12px', fontWeight:600,
                  background: saved === user.id ? '#276749' : '#6B46C1',
                  color:'#fff', border:'none', cursor:'pointer',
                  opacity: saving === user.id ? 0.6 : 1,
                }}>
                {saving === user.id ? '⏳' : saved === user.id ? '✅ Saved' : '💾 Save'}
              </button>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'6px' }}>
              {ALL_PANELS.map(panel => {
                const granted = (perms[user.id] || new Set()).has(panel.id)
                return (
                  <label key={panel.id} style={{
                    display:'flex', alignItems:'center', gap:'8px',
                    padding:'6px 8px', borderRadius:'6px', cursor:'pointer',
                    background: granted ? '#F0FFF4' : C.white,
                    border:`1px solid ${granted ? '#9AE6B4' : C.border}`,
                    transition:'all 0.15s',
                  }}>
                    <input
                      type="checkbox"
                      checked={granted}
                      onChange={() => togglePerm(user.id, panel.id)}
                      style={{ accentColor:'#276749', width:'14px', height:'14px' }}
                    />
                    <div>
                      <div style={{ fontSize:'12px', fontWeight:600, color: granted ? '#276749' : C.text }}>{panel.label}</div>
                      <div style={{ fontSize:'10px', color:C.textMuted }}>{panel.desc}</div>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Staff Compliance Panel ────────────────────────────────────────────────────
function StaffPanel({ onClose, authToken = '' }) {
  const C = useTheme()
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState('all')   // all | alerts | role
  const [expanded, setExpanded] = useState(null)   // expanded staff name

  useEffect(() => {
    setLoading(true)
    fetch(`${API}/api/staff/compliance`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    })
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(d => { setData(d); setLoading(false) })
  }, [authToken])

  const LEVEL_META = {
    overdue:  { bg:'#FFF0F0', color:'#C53030', dot:'🔴', label:'OVERDUE'  },
    critical: { bg:'#FFF5F0', color:'#C05020', dot:'🟠', label:'< 14 days' },
    warn:     { bg:'#FFFFF0', color:'#8A6020', dot:'🟡', label:'< 30 days' },
    ok:       { bg:'#F0FFF4', color:'#276749', dot:'🟢', label:'OK'        },
    na:       { bg:C.bgSecondary, color:C.textMuted, dot:'—', label:'N/A'  },
  }

  const BadgeCell = ({ field }) => {
    const m = LEVEL_META[field.level] || LEVEL_META.na
    const days = field.days
    return (
      <div style={{
        display:'inline-flex', alignItems:'center', gap:'4px',
        background:m.bg, color:m.color,
        borderRadius:'6px', padding:'3px 7px', fontSize:'11px', fontWeight:700,
        whiteSpace:'nowrap',
      }}>
        {m.dot}
        {field.level === 'ok' && days !== null ? `${days}d` :
         field.level === 'na' ? '—' :
         field.level === 'overdue' ? `${Math.abs(days)}d ago` :
         `${days}d`}
      </div>
    )
  }

  const filtered = !data ? [] : data.staff.filter(s => {
    if (filter === 'alerts') return ['overdue','critical','warn'].includes(s.overall)
    return true
  })

  const panelStyle = {
    position:'fixed', top:0, right:0, width:'min(640px, 100vw)', height:'100vh',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    display:'flex', flexDirection:'column', zIndex:500,
    boxShadow:'-4px 0 32px rgba(0,0,0,0.12)',
  }

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center', flexShrink:0 }}>
        <div>
          <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>👥 Staff Compliance</div>
          {data && <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>
            {data.summary.overdue} overdue · {data.summary.critical} critical · {data.summary.warn} expiring soon · as of today
          </div>}
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'22px', cursor:'pointer', color:C.textMuted, lineHeight:1 }}>×</button>
      </div>

      {/* Alert banner */}
      {data && (data.summary.overdue > 0 || data.summary.critical > 0) && (
        <div style={{
          background: data.summary.overdue > 0 ? '#FFF0F0' : '#FFF5F0',
          borderBottom: `2px solid ${data.summary.overdue > 0 ? '#FC8181' : '#ED8936'}`,
          padding:'10px 18px', flexShrink:0,
        }}>
          <div style={{ fontWeight:700, fontSize:'12px', color: data.summary.overdue > 0 ? '#C53030' : '#C05020' }}>
            ⚠️ DOH Alert Risk
          </div>
          <div style={{ fontSize:'11px', color: data.summary.overdue > 0 ? '#742A2A' : '#7B341E', marginTop:'3px' }}>
            {data.summary.overdue > 0 && `${data.summary.overdue} staff member(s) have OVERDUE documents — act immediately to avoid citations.`}
            {data.summary.overdue === 0 && `${data.summary.critical} staff member(s) expire within 14 days.`}
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div style={{ display:'flex', gap:'4px', padding:'8px 18px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {[{id:'all',label:'All Staff'},{id:'alerts',label:`⚠️ Alerts (${data ? data.summary.overdue + data.summary.critical + data.summary.warn : '…'})`}].map(t => (
          <button key={t.id} onClick={() => setFilter(t.id)} style={{
            padding:'5px 14px', borderRadius:'8px', border:'none', cursor:'pointer', fontSize:'12px',
            background: filter===t.id ? C.blue : C.bgSecondary,
            color: filter===t.id ? '#fff' : C.textMid, fontWeight: filter===t.id ? 700 : 400,
          }}>{t.label}</button>
        ))}
      </div>

      {/* Column headers */}
      <div style={{
        display:'grid', gridTemplateColumns:'1fr 80px 80px 80px 80px',
        gap:'6px', padding:'7px 18px', borderBottom:`1px solid ${C.border}`,
        flexShrink:0,
      }}>
        {['Employee','Medical','TB/Xray','CPR','Inservice'].map(h => (
          <div key={h} style={{ fontSize:'10px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', letterSpacing:'0.4px',
            textAlign: h === 'Employee' ? 'left' : 'center' }}>{h}</div>
        ))}
      </div>

      {/* Staff rows */}
      <div style={{ flex:1, overflowY:'auto' }}>
        {loading ? (
          <div style={{ textAlign:'center', color:C.textMuted, marginTop:'48px', fontSize:'14px' }}>Loading compliance data…</div>
        ) : !filtered.length ? (
          <div style={{ textAlign:'center', color:C.textMuted, marginTop:'48px', fontSize:'14px' }}>No alerts — everyone is current ✅</div>
        ) : filtered.map(s => {
          const meta   = LEVEL_META[s.overall] || LEVEL_META.na
          const isOpen = expanded === s.name
          return (
            <div key={s.name} style={{ borderBottom:`1px solid ${C.border}` }}>
              {/* Row */}
              <button onClick={() => setExpanded(isOpen ? null : s.name)} style={{
                display:'grid', gridTemplateColumns:'1fr 80px 80px 80px 80px',
                gap:'6px', width:'100%', padding:'10px 18px',
                background: isOpen ? C.bgSecondary : 'transparent',
                border:'none', cursor:'pointer', textAlign:'left',
                alignItems:'center',
              }}>
                {/* Name + role */}
                <div>
                  <div style={{ display:'flex', alignItems:'center', gap:'7px' }}>
                    <div style={{
                      width:'8px', height:'8px', borderRadius:'50%', flexShrink:0,
                      background: meta.color,
                    }} />
                    <span style={{ fontWeight:600, fontSize:'13px', color:C.text }}>{s.name}</span>
                  </div>
                  <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px', marginLeft:'15px' }}>{s.role}</div>
                </div>
                {/* Doc badges */}
                {[s.medical, s.tb, s.cpr, s.inservice].map((f, i) => (
                  <div key={i} style={{ display:'flex', justifyContent:'center' }}>
                    <BadgeCell field={f} />
                  </div>
                ))}
              </button>

              {/* Expanded detail */}
              {isOpen && (
                <div style={{ padding:'10px 18px 14px 33px', background:C.bgSecondary, borderTop:`1px solid ${C.border}` }}>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px' }}>
                    {[
                      { label:'Medical Physical', ...s.medical },
                      { label:`TB / ${s.tb_type || 'Quanti/Xray'}`, ...s.tb },
                      { label:'CPR / First Aid', ...s.cpr },
                      { label:'Inservice Hours', ...s.inservice },
                    ].map(f => {
                      const m = LEVEL_META[f.level] || LEVEL_META.na
                      return (
                        <div key={f.label} style={{ background:m.bg, borderRadius:'8px', padding:'8px 10px' }}>
                          <div style={{ fontSize:'10px', fontWeight:700, color:C.textMuted, textTransform:'uppercase', marginBottom:'4px' }}>{f.label}</div>
                          <div style={{ fontSize:'12px', fontWeight:700, color:m.color }}>
                            {m.dot} {f.due ? new Date(f.due + 'T00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : 'N/A'}
                          </div>
                          {f.days !== null && f.level !== 'na' && (
                            <div style={{ fontSize:'11px', color:m.color, marginTop:'2px' }}>
                              {f.level === 'overdue' ? `${Math.abs(f.days)} days overdue` :
                               f.level === 'ok'      ? `${f.days} days remaining` :
                                                       `${f.days} days remaining`}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                  {s.hire_date && <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'8px' }}>Hire date: {s.hire_date}</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}


// ── Attendance Panel ──────────────────────────────────────────────────────────
function AttendancePanel({ onClose }) {
  const C = useTheme()
  const todayISO = new Date().toISOString().slice(0,10)
  const [date,    setDate]    = useState(todayISO)
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [shift,   setShift]   = useState('1')

  const load = (d) => {
    setLoading(true)
    setData(null)
    fetch(`${API}/api/attendance?date=${d}`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
      .then(d => { setData(d); setLoading(false) })
  }

  useEffect(() => { load(date) }, [date])

  const STATUS_META = {
    present:   { bg:'#F0FFF4', color:'#276749', dot:'●', label:'Present'   },
    attended:  { bg:'#F0FFF4', color:'#276749', dot:'●', label:'Present'   },
    scheduled: { bg:'#EBF4FF', color:'#2B6CB0', dot:'○', label:'Scheduled' },
    absent:    { bg:'#FFF5F5', color:'#C53030', dot:'✕', label:'Absent'    },
  }

  const clients = data?.shifts?.[shift] || []
  const shifts  = data ? Object.keys(data.shifts).sort() : []
  const allClients = data ? Object.values(data.shifts).flat() : []
  const presentCount   = allClients.filter(c => ['present','attended'].includes(c.status)).length
  const scheduledCount = allClients.length

  const prevDay = () => {
    const d = new Date(date + 'T12:00'); d.setDate(d.getDate()-1)
    setDate(d.toISOString().slice(0,10))
  }
  const nextDay = () => {
    const d = new Date(date + 'T12:00'); d.setDate(d.getDate()+1)
    setDate(d.toISOString().slice(0,10))
  }

  const panelStyle = {
    position:'fixed', top:0, right:0, width:'min(480px, 100vw)', height:'100vh',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    display:'flex', flexDirection:'column', zIndex:500,
    boxShadow:'-4px 0 32px rgba(0,0,0,0.12)',
  }

  const dateLabel = new Date(date+'T12:00').toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'})

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ padding:'14px 18px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center', flexShrink:0 }}>
        <div>
          <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>📋 Client Attendance</div>
          {data && !loading && (
            <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>
              {presentCount} present · {scheduledCount} scheduled
            </div>
          )}
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'22px', cursor:'pointer', color:C.textMuted, lineHeight:1 }}>×</button>
      </div>

      {/* Date nav */}
      <div style={{ display:'flex', alignItems:'center', gap:'8px', padding:'10px 18px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        <button onClick={prevDay} style={{ width:'32px', height:'32px', borderRadius:'8px', border:`1px solid ${C.border}`, background:C.bgSecondary, cursor:'pointer', fontSize:'15px', color:C.text, display:'flex', alignItems:'center', justifyContent:'center' }}>‹</button>
        <div style={{ flex:1, textAlign:'center' }}>
          <div style={{ fontWeight:600, fontSize:'13px', color:C.text }}>{dateLabel}</div>
          {date === todayISO && <div style={{ fontSize:'10px', color:C.blue, fontWeight:700, marginTop:'2px' }}>TODAY</div>}
        </div>
        <button onClick={nextDay} style={{ width:'32px', height:'32px', borderRadius:'8px', border:`1px solid ${C.border}`, background:C.bgSecondary, cursor:'pointer', fontSize:'15px', color:C.text, display:'flex', alignItems:'center', justifyContent:'center' }}>›</button>
      </div>

      {/* Stats bar */}
      {data && !loading && scheduledCount > 0 && (
        <div style={{ display:'flex', gap:'0', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
          {[
            { label:'Scheduled', count:scheduledCount, bg:'#EBF4FF', color:'#2B6CB0' },
            { label:'Present',   count:presentCount,   bg:'#F0FFF4', color:'#276749' },
            { label:'Not Logged',count:scheduledCount-presentCount, bg:'#FAFAFA', color:C.textMuted },
          ].map(s => (
            <div key={s.label} style={{ flex:1, padding:'10px 0', textAlign:'center', background:s.bg }}>
              <div style={{ fontSize:'22px', fontWeight:800, color:s.color, lineHeight:1 }}>{s.count}</div>
              <div style={{ fontSize:'10px', color:s.color, marginTop:'3px', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.3px' }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Shift tabs */}
      {shifts.length > 1 && (
        <div style={{ display:'flex', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
          {shifts.map(s => (
            <button key={s} onClick={() => setShift(s)} style={{
              flex:1, padding:'9px', border:'none', cursor:'pointer', fontSize:'13px',
              fontWeight: shift===s ? 700 : 400,
              borderBottom: shift===s ? `3px solid ${C.blue}` : '3px solid transparent',
              background: 'transparent',
              color: shift===s ? C.blue : C.textMid,
            }}>Shift {s} <span style={{ fontSize:'11px', color:C.textMuted }}>({(data?.shifts?.[s]||[]).length})</span></button>
          ))}
        </div>
      )}

      {/* Client list */}
      <div style={{ flex:1, overflowY:'auto' }}>
        {loading ? (
          <div style={{ textAlign:'center', color:C.textMuted, marginTop:'60px', fontSize:'14px' }}>Loading…</div>
        ) : !clients.length ? (
          <div style={{ textAlign:'center', padding:'48px 24px' }}>
            <div style={{ fontSize:'36px', marginBottom:'12px' }}>📋</div>
            <div style={{ fontSize:'14px', color:C.textMuted }}>No attendance data for this date</div>
            <div style={{ fontSize:'12px', color:C.textMuted, marginTop:'6px' }}>
              Drop a scanned sign-in sheet into the signins/ folder to populate this.
            </div>
          </div>
        ) : (
          <div>
            {clients.map((c, i) => {
              const m = STATUS_META[c.status] || STATUS_META.scheduled
              return (
                <div key={c.name} style={{
                  display:'flex', alignItems:'center', gap:'12px',
                  padding:'11px 18px',
                  borderBottom:`1px solid ${C.border}`,
                  background: i % 2 === 0 ? C.white : C.bgSecondary,
                }}>
                  {/* Status dot */}
                  <div style={{
                    width:'10px', height:'10px', borderRadius:'50%', flexShrink:0,
                    background: m.color,
                    opacity: c.status === 'scheduled' ? 0.35 : 1,
                    border: c.status === 'scheduled' ? `2px solid ${m.color}` : 'none',
                  }} />
                  {/* Name */}
                  <div style={{ flex:1 }}>
                    <span style={{ fontSize:'13px', fontWeight:600, color: c.status === 'absent' ? '#C53030' : C.text }}>
                      {c.name}
                    </span>
                    {c.source && <span style={{ fontSize:'10px', color:C.textMuted, marginLeft:'6px' }}>· {c.source}</span>}
                  </div>
                  {/* Status badge */}
                  <div style={{
                    fontSize:'10px', fontWeight:700, padding:'3px 8px', borderRadius:'6px',
                    background:m.bg, color:m.color, textTransform:'uppercase', letterSpacing:'0.3px',
                    flexShrink:0,
                  }}>
                    {m.label}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer note */}
      <div style={{ padding:'10px 18px', borderTop:`1px solid ${C.border}`, flexShrink:0 }}>
        <div style={{ fontSize:'10px', color:C.textMuted }}>
          Data sourced from scanned sign-in sheets · Drop PDFs in <code style={{ background:C.bgSecondary, padding:'1px 4px', borderRadius:'3px' }}>signins/</code> to update
        </div>
      </div>
    </div>
  )
}


// ── Chairman Audit Trail Panel ─────────────────────────────────────────────────
function ChairmanAuditPanel({ onClose }) {
  const C = useTheme()
  const [events,  setEvents]  = useState([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState('all')
  const [search,  setSearch]  = useState('')

  useEffect(() => {
    fetch(`${API}/api/audit?limit=500`)
      .then(r => r.ok ? r.json() : { events: [] })
      .then(d => { setEvents(d.events || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const EVENT_ICONS = {
    APP_START:'🟢', APP_STOP:'🔴', SECURE_MODE_ON:'🛡', SECURE_MODE_OFF:'🔓',
    MESSAGE_SENT:'💬', RESPONSE_RECEIVED:'🤖', PHI_DETECTED:'⚠️', PHI_REDACTED:'🔒',
    JOURNEY_CREATED:'📝', JOURNEY_VIEWED:'👁', JOURNEY_EXPORTED:'📤',
    API_KEY_SET:'🔑', API_KEY_REMOVED:'🗑', MODEL_CHANGED:'🔄',
    DEVICE_PAIRED:'📱', OLLAMA_REROUTE:'⚡', RESPONSE_SCAN_FAIL:'🚨',
    RESPONSE_SCAN_PASS:'✅',
  }

  const EVENT_CATEGORIES = {
    security: ['SECURE_MODE_ON','SECURE_MODE_OFF','PHI_DETECTED','PHI_REDACTED','RESPONSE_SCAN_FAIL','RESPONSE_SCAN_PASS'],
    access:   ['JOURNEY_VIEWED','JOURNEY_CREATED','JOURNEY_EXPORTED','MESSAGE_SENT','RESPONSE_RECEIVED'],
    system:   ['APP_START','APP_STOP','API_KEY_SET','API_KEY_REMOVED','MODEL_CHANGED','DEVICE_PAIRED','OLLAMA_REROUTE'],
  }

  const filtered = events.filter(e => {
    if (filter !== 'all' && !EVENT_CATEGORIES[filter]?.includes(e.event_type)) return false
    if (search && !e.event_type.toLowerCase().includes(search.toLowerCase()) &&
        !JSON.stringify(e.details||{}).toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const fmtTime = ts => {
    if (!ts) return ''
    const d = new Date(ts)
    return d.toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'})
  }

  const panelStyle = {
    position:'fixed', top:0, right:0, width:'420px', height:'100vh',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    display:'flex', flexDirection:'column', zIndex:500,
    boxShadow:'-4px 0 24px rgba(0,0,0,0.10)',
  }

  const FILTER_TABS = [
    {id:'all',label:'All'},
    {id:'security',label:'🛡 Security'},
    {id:'access',label:'👁 Access'},
    {id:'system',label:'⚙ System'},
  ]

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ padding:'16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'10px' }}>
          <div>
            <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>👁 Chairman Audit Trail</div>
            <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px' }}>All system actions · HIPAA §164.312(b)</div>
          </div>
          <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'20px', cursor:'pointer', color:C.textMuted }}>×</button>
        </div>
        {/* Search */}
        <input
          value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="Search events…"
          style={{ width:'100%', padding:'7px 10px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px', color:C.text, background:C.bgSecondary, boxSizing:'border-box' }}
        />
      </div>

      {/* Filter tabs */}
      <div style={{ display:'flex', gap:'4px', padding:'8px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {FILTER_TABS.map(t => (
          <button key={t.id} onClick={()=>setFilter(t.id)} style={{
            padding:'4px 10px', borderRadius:'8px', border:'none', cursor:'pointer', fontSize:'12px',
            background: filter===t.id ? C.blue : C.bgSecondary,
            color: filter===t.id ? '#fff' : C.textMid, fontWeight: filter===t.id ? 700 : 400,
          }}>{t.label}</button>
        ))}
        <span style={{ marginLeft:'auto', fontSize:'11px', color:C.textMuted, alignSelf:'center' }}>{filtered.length} events</span>
      </div>

      {/* Events list */}
      <div style={{ flex:1, overflowY:'auto', padding:'8px 0' }}>
        {loading ? (
          <div style={{ textAlign:'center', color:C.textMuted, marginTop:'32px' }}>Loading audit trail…</div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign:'center', color:C.textMuted, marginTop:'32px', fontSize:'13px' }}>No events match</div>
        ) : filtered.map((e,i) => {
          const icon = EVENT_ICONS[e.event_type] || '📋'
          const isAlert = ['PHI_DETECTED','RESPONSE_SCAN_FAIL','API_KEY_REMOVED'].includes(e.event_type)
          const isSecurity = EVENT_CATEGORIES.security.includes(e.event_type)
          const details = e.details || {}
          const detailStr = Object.entries(details)
            .filter(([k]) => !['id'].includes(k))
            .map(([k,v]) => `${k}: ${v}`)
            .join(' · ')

          return (
            <div key={e.id||i} style={{
              padding:'10px 16px',
              borderBottom:`1px solid ${C.border}`,
              background: isAlert ? '#FFF0F0' : 'transparent',
              borderLeft: isAlert ? '3px solid #CF222E' : isSecurity ? `3px solid ${C.blue}` : '3px solid transparent',
            }}>
              <div style={{ display:'flex', alignItems:'flex-start', gap:'8px' }}>
                <span style={{ fontSize:'16px', flexShrink:0, marginTop:'1px' }}>{icon}</span>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <span style={{ fontSize:'12px', fontWeight:700, color: isAlert ? '#CF222E' : C.text }}>
                      {e.event_type.replace(/_/g,' ')}
                    </span>
                    <span style={{ fontSize:'10px', color:C.textMuted, flexShrink:0, marginLeft:'8px' }}>
                      {fmtTime(e.timestamp)}
                    </span>
                  </div>
                  {detailStr && (
                    <div style={{ fontSize:'11px', color:C.textMuted, marginTop:'2px', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                      {detailStr}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div style={{ padding:'10px 16px', borderTop:`1px solid ${C.border}`, flexShrink:0, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <span style={{ fontSize:'11px', color:C.textMuted }}>{events.length} total events stored</span>
        <button onClick={()=>{
          fetch(`${API}/api/audit?limit=500`).then(r=>r.json()).then(d=>{setEvents(d.events||[])})
        }} style={{ fontSize:'12px', color:C.blue, background:'none', border:'none', cursor:'pointer', fontWeight:600 }}>↻ Refresh</button>
      </div>
    </div>
  )
}

// ── EDI 837 / 835 Panel ───────────────────────────────────────────────────────
// ── GOJ Stats Panel ──────────────────────────────────────────────────────────
function GOJStatsPanel({ onClose, authToken = '' }) {
  const C = useTheme()
  const API = window.REX_API_URL || 'http://localhost:8000'
  const [stats, setStats] = useState(null)
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview') // overview | members | roster
  const [search, setSearch] = useState('')
  const [filterPlan, setFilterPlan] = useState('')
  const headers = { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' }

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/api/goj/stats`, { headers }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API}/api/goj/members`, { headers }).then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([s, m]) => {
      setStats(s)
      setMembers(m?.members || [])
      setLoading(false)
    })
  }, [])

  const PLAN_COLORS = {
    'CPHL': '#3182CE', 'Eld Serve': '#38A169', 'Anthem': '#D69E2E',
    'VCM': '#805AD5', 'SWH': '#E53E3E', 'VNS': '#DD6B20',
    'Aetna': '#319795', 'MetroPlus': '#2D3748', 'Pr.Pay': '#718096', 'Empire': '#9F7AEA',
  }

  const filteredMembers = members.filter(m => {
    const matchSearch = !search || m.name.toLowerCase().includes(search.toLowerCase())
    const matchPlan = !filterPlan || m.plan === filterPlan
    return matchSearch && matchPlan
  })

  const tabStyle = (active) => ({
    padding: '6px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 600,
    cursor: 'pointer', transition: 'all 0.2s',
    background: active ? '#276749' : C.bgSecondary,
    color: active ? '#fff' : C.textMid,
    border: `1px solid ${active ? '#276749' : C.border}`,
  })

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '20px', marginTop: '12px' }}>
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'16px' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
          <span style={{ fontSize:'20px' }}>🏥</span>
          <div>
            <div style={{ fontWeight:700, fontSize:'16px', color: C.text }}>Garden of Joy — Member Intelligence</div>
            <div style={{ fontSize:'11px', color: C.textMuted, fontFamily:'monospace' }}>
              {stats?.meta?.totalMembers || 425} members · Live from Google Sheets · {stats?.source === 'live' ? '🟢 Live' : '🟡 Cached'}
            </div>
          </div>
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', color: C.textMuted, fontSize:'20px', cursor:'pointer' }}>✕</button>
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:'8px', marginBottom:'16px', flexWrap:'wrap' }}>
        {['overview','members','roster'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={tabStyle(tab === t)}>
            {t === 'overview' ? '📊 Overview' : t === 'members' ? '👥 Members' : '📋 Daily Rosters'}
          </button>
        ))}
      </div>

      {loading && <div style={{ textAlign:'center', color: C.textMuted, padding:'40px' }}>Loading GOJ data...</div>}

      {!loading && tab === 'overview' && stats && (
        <div>
          {/* Big stats row */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(120px, 1fr))', gap:'12px', marginBottom:'20px' }}>
            {[
              { label:'Total Members', value: stats.meta?.totalMembers || 425, color:'#276749' },
              { label:'Van Transport', value: stats.transport?.van || 357, color:'#2B6CB0' },
              { label:'Self Transport', value: stats.transport?.self || 68, color:'#805AD5' },
              { label:'CDPAP', value: stats.cdpap || 216, color:'#C05621' },
            ].map(s => (
              <div key={s.label} style={{ background: C.bgSecondary, borderRadius:'10px', padding:'14px', textAlign:'center', border:`1px solid ${C.border}` }}>
                <div style={{ fontSize:'26px', fontWeight:800, color: s.color }}>{s.value}</div>
                <div style={{ fontSize:'11px', color: C.textMuted, marginTop:'4px' }}>{s.label}</div>
              </div>
            ))}
          </div>

          {/* Plan breakdown */}
          <div style={{ marginBottom:'20px' }}>
            <div style={{ fontSize:'13px', fontWeight:600, color: C.textMid, marginBottom:'10px' }}>Insurance Plan Breakdown</div>
            <div style={{ display:'flex', flexDirection:'column', gap:'6px' }}>
              {Object.entries(stats.plans || {}).sort((a,b) => b[1]-a[1]).map(([plan, cnt]) => {
                const total = stats.meta?.totalMembers || 425
                const pct = Math.round((cnt / total) * 100)
                return (
                  <div key={plan} style={{ display:'flex', alignItems:'center', gap:'10px' }}>
                    <div style={{ width:'90px', fontSize:'12px', color: C.text, fontWeight:500, flexShrink:0 }}>{plan}</div>
                    <div style={{ flex:1, background: C.bgSecondary, borderRadius:'4px', height:'18px', overflow:'hidden' }}>
                      <div style={{ width:`${pct}%`, background: PLAN_COLORS[plan] || '#718096', height:'100%', borderRadius:'4px', transition:'width 0.5s' }} />
                    </div>
                    <div style={{ width:'70px', fontSize:'12px', color: C.textMuted, textAlign:'right', fontFamily:'monospace' }}>{cnt} ({pct}%)</div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Daily attendance */}
          <div style={{ marginBottom:'20px' }}>
            <div style={{ fontSize:'13px', fontWeight:600, color: C.textMid, marginBottom:'10px' }}>Daily Scheduled Attendance</div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:'8px' }}>
              {Object.entries(stats.byDay || { M:150, T:146, W:166, TH:159, F:206, Su:64 }).map(([day, cnt]) => (
                <div key={day} style={{ background: C.bgSecondary, borderRadius:'8px', padding:'10px', textAlign:'center', border:`1px solid ${C.border}` }}>
                  <div style={{ fontSize:'18px', fontWeight:700, color:'#2B6CB0' }}>{cnt}</div>
                  <div style={{ fontSize:'11px', color: C.textMuted, marginTop:'2px' }}>{day}</div>
                </div>
              ))}
            </div>
          </div>

          {/* April 2026 attendance */}
          {stats.aprilByDay && Object.keys(stats.aprilByDay).length > 0 && (
            <div>
              <div style={{ fontSize:'13px', fontWeight:600, color: C.textMid, marginBottom:'10px' }}>April 2026 Daily Attendance (Actual)</div>
              <div style={{ display:'flex', gap:'6px', flexWrap:'wrap' }}>
                {Object.entries(stats.aprilByDay).map(([day, cnt]) => (
                  <div key={day} style={{ background: C.bgSecondary, borderRadius:'6px', padding:'8px 10px', textAlign:'center', border:`1px solid ${C.border}`, minWidth:'52px' }}>
                    <div style={{ fontSize:'16px', fontWeight:700, color:'#276749' }}>{cnt}</div>
                    <div style={{ fontSize:'10px', color: C.textMuted }}>Apr {day}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && tab === 'members' && (
        <div>
          <div style={{ display:'flex', gap:'8px', marginBottom:'12px', flexWrap:'wrap' }}>
            <input
              value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search member name..."
              style={{ flex:1, minWidth:'180px', padding:'8px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, background: C.bgSecondary, color: C.text, fontSize:'13px' }}
            />
            <select value={filterPlan} onChange={e => setFilterPlan(e.target.value)}
              style={{ padding:'8px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, background: C.bgSecondary, color: C.text, fontSize:'13px' }}>
              <option value="">All Plans</option>
              {Object.keys(PLAN_COLORS).map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div style={{ fontSize:'12px', color: C.textMuted, marginBottom:'8px' }}>{filteredMembers.length} members shown</div>
          <div style={{ maxHeight:'420px', overflowY:'auto', display:'flex', flexDirection:'column', gap:'6px' }}>
            {filteredMembers.slice(0, 100).map((m, i) => (
              <div key={i} style={{ display:'grid', gridTemplateColumns:'200px 90px 60px 1fr auto', gap:'10px', alignItems:'center', padding:'8px 12px', background: C.bgSecondary, borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px' }}>
                <div style={{ fontWeight:600, color: C.text, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{m.name}</div>
                <div>
                  <span style={{ background: PLAN_COLORS[m.plan] || '#718096', color:'#fff', borderRadius:'4px', padding:'2px 6px', fontSize:'11px', fontWeight:600 }}>{m.plan}</span>
                </div>
                <div style={{ fontSize:'11px', color: m.transport === 'TR' ? '#2B6CB0' : C.textMuted }}>
                  {m.transport === 'TR' ? '🚌 Van' : '🚶 Self'}
                </div>
                <div style={{ fontSize:'11px', color: C.textMuted, fontFamily:'monospace' }}>
                  {Object.entries(m.days || {}).filter(([,v])=>v).map(([d])=>d).join(' ')}
                </div>
                <div style={{ fontSize:'11px', color: m.cdpap === 'yes' ? '#276749' : 'transparent' }}>CDPAP</div>
              </div>
            ))}
            {filteredMembers.length > 100 && <div style={{ textAlign:'center', color: C.textMuted, fontSize:'12px', padding:'8px' }}>Showing first 100 of {filteredMembers.length} — use search to narrow</div>}
            {members.length === 0 && <div style={{ textAlign:'center', color: C.textMuted, padding:'30px', fontSize:'13px' }}>No member data loaded. Run <code>tools/goj_import.py</code> to import from Google Sheets.</div>}
          </div>
        </div>
      )}

      {!loading && tab === 'roster' && (
        <div>
          <div style={{ fontSize:'13px', color: C.textMuted, marginBottom:'12px' }}>Daily shift rosters from master sign-in sheet (current schedule)</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(160px, 1fr))', gap:'10px' }}>
            {Object.entries(stats?.dailyRosters || { M1:77,M2:73,T1:86,T2:60,W1:78,W2:88,TH1:94,TH2:65,F1:98,F2:108,Su:64 }).map(([shift, cnt]) => {
              const dayName = { M:'Monday', T:'Tuesday', W:'Wednesday', TH:'Thursday', F:'Friday', Su:'Sunday' }
              const day = shift.replace(/\d+/, '')
              return (
                <div key={shift} style={{ background: C.bgSecondary, borderRadius:'10px', padding:'12px', border:`1px solid ${C.border}`, textAlign:'center' }}>
                  <div style={{ fontSize:'22px', fontWeight:800, color:'#2B6CB0' }}>{cnt}</div>
                  <div style={{ fontSize:'12px', fontWeight:600, color: C.text }}>{shift}</div>
                  <div style={{ fontSize:'11px', color: C.textMuted }}>{dayName[day]} Shift {shift.replace(/[A-Z]+/, '')}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Document Vault Panel ──────────────────────────────────────────────────────
function DocumentVaultPanel({ onClose, authToken = '' }) {
  const C = useTheme()
  const API = window.REX_API_URL || 'http://localhost:8000'
  const [docs, setDocs] = useState([])
  const [medicalPortfolio, setMedicalPortfolio] = useState({})
  const [memberPortfolios, setMemberPortfolios] = useState({ shared_docs: [], per_member: {}, goj_member_count: 0, shared_doc_count: 0, total_members_with_docs: 0 })
  const [loading, setLoading] = useState(true)
  const [routing, setRouting] = useState(false)
  const [routeResult, setRouteResult] = useState(null)
  const [tab, setTab] = useState('overview') // overview | staff | members | compliance
  const [memberSearch, setMemberSearch] = useState('')
  const [uploadingFor, setUploadingFor] = useState(null)
  const headers = { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' }

  const loadAll = () => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/api/documents`, { headers }).then(r => r.ok ? r.json() : { documents: [] }).catch(() => ({ documents: [] })),
      fetch(`${API}/api/staff/medical`, { headers }).then(r => r.ok ? r.json() : { portfolio: {} }).catch(() => ({ portfolio: {} })),
      fetch(`${API}/api/members/portfolios`, { headers }).then(r => r.ok ? r.json() : {}).catch(() => ({})),
    ]).then(([d, m, mp]) => {
      setDocs(d.documents || [])
      setMedicalPortfolio(m.portfolio || {})
      setMemberPortfolios(mp || { shared_docs: [], per_member: {}, goj_member_count: 0, shared_doc_count: 0, total_members_with_docs: 0 })
      setLoading(false)
    })
  }

  useEffect(() => { loadAll() }, [])

  const handleRouteDocuments = () => {
    if (!window.confirm('Download and route all email attachments to their correct folders? This will pull from Gmail and may take a minute.')) return
    setRouting(true)
    fetch(`${API}/api/documents/route`, { method: 'POST', headers })
      .then(r => r.ok ? r.json() : null)
      .then(result => {
        setRouteResult(result)
        setRouting(false)
        loadAll()
      })
      .catch(() => setRouting(false))
  }

  const handleUploadForMember = async (memberName, file) => {
    if (!file) return
    const fd = new FormData()
    fd.append('member_name', memberName)
    fd.append('file', file)
    setUploadingFor(memberName)
    try {
      const res = await fetch(`${API}/api/members/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${authToken}` },
        body: fd,
      })
      if (res.ok) loadAll()
    } finally {
      setUploadingFor(null)
    }
  }

  const tabStyle = (active) => ({
    padding: '6px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 600,
    cursor: 'pointer', transition: 'all 0.2s',
    background: active ? '#C05621' : C.bgSecondary,
    color: active ? '#fff' : C.textMid,
    border: `1px solid ${active ? '#C05621' : C.border}`,
  })

  const CAT_LABELS = {
    'staff_medical':    { icon:'🩺', label:'Staff Medical', color:'#2B6CB0' },
    'staff_inservice':  { icon:'📋', label:'Inservice Logs', color:'#276749' },
    'compliance_audit': { icon:'🔒', label:'Audit Vault', color:'#E53E3E' },
    'site_visit':       { icon:'🏛', label:'Site Visit Docs', color:'#805AD5' },
    'signin_scan':      { icon:'✍️', label:'Sign-in Scans', color:'#D69E2E' },
    'menu_scan':        { icon:'🍽', label:'Menu Scans', color:'#DD6B20' },
    'general_scan':     { icon:'📄', label:'General Scans', color:'#718096' },
  }
  const categoryCounts = {}
  docs.forEach(d => { categoryCounts[d.category] = (categoryCounts[d.category] || 0) + 1 })

  // Filter member portfolios by search
  const filteredMemberPortfolios = Object.entries(memberPortfolios.per_member || {}).filter(([name]) =>
    !memberSearch || name.toLowerCase().includes(memberSearch.toLowerCase())
  )

  return (
    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '20px', marginTop: '12px' }}>

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'16px' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'10px' }}>
          <span style={{ fontSize:'20px' }}>📁</span>
          <div>
            <div style={{ fontWeight:700, fontSize:'16px', color: C.text }}>Document Vault</div>
            <div style={{ fontSize:'11px', color: C.textMuted, fontFamily:'monospace' }}>
              {docs.length} files · {Object.keys(medicalPortfolio).length} staff · {memberPortfolios.goj_member_count || 0} members · {memberPortfolios.shared_doc_count || 0} shared auth docs
            </div>
          </div>
        </div>
        <div style={{ display:'flex', gap:'8px', alignItems:'center' }}>
          <button onClick={handleRouteDocuments} disabled={routing}
            style={{ padding:'6px 14px', borderRadius:'8px', fontSize:'12px', fontWeight:600, cursor:routing?'wait':'pointer',
              background:'#C05621', color:'#fff', border:'none', opacity: routing ? 0.6 : 1 }}>
            {routing ? '⏳ Routing...' : '📥 Route Emails'}
          </button>
          <button onClick={onClose} style={{ background:'none', border:'none', color: C.textMuted, fontSize:'20px', cursor:'pointer' }}>✕</button>
        </div>
      </div>

      {routeResult && (
        <div style={{ background:'#276749', color:'#fff', borderRadius:'8px', padding:'10px 14px', marginBottom:'12px', fontSize:'13px' }}>
          ✓ Routed {routeResult.total_files} files across {routeResult.routes?.length} email threads. Shared auth docs extracted to member portfolios.
        </div>
      )}

      {/* Tabs */}
      <div style={{ display:'flex', gap:'8px', marginBottom:'16px', flexWrap:'wrap' }}>
        {[['overview','📊 Overview'],['members','👥 Members'],['staff','🩺 Staff'],['compliance','🔒 Compliance']].map(([t,label]) => (
          <button key={t} onClick={() => setTab(t)} style={tabStyle(tab===t)}>{label}</button>
        ))}
      </div>

      {/* ── OVERVIEW TAB ── */}
      {tab === 'overview' && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(130px, 1fr))', gap:'10px' }}>
          {/* Member portfolios card */}
          <div style={{ background: C.bgSecondary, borderRadius:'10px', padding:'12px', border:`2px solid #276749`, textAlign:'center' }}>
            <div style={{ fontSize:'20px', marginBottom:'4px' }}>👥</div>
            <div style={{ fontSize:'22px', fontWeight:800, color:'#276749' }}>{memberPortfolios.goj_member_count || 0}</div>
            <div style={{ fontSize:'11px', color: C.textMuted }}>Members</div>
            {(memberPortfolios.shared_doc_count || 0) > 0 && (
              <div style={{ fontSize:'10px', color:'#276749', marginTop:'4px' }}>{memberPortfolios.shared_doc_count} shared auth docs</div>
            )}
          </div>
          {/* Staff medical */}
          <div style={{ background: C.bgSecondary, borderRadius:'10px', padding:'12px', border:`1px solid ${C.border}`, textAlign:'center' }}>
            <div style={{ fontSize:'20px', marginBottom:'4px' }}>🩺</div>
            <div style={{ fontSize:'22px', fontWeight:800, color:'#2B6CB0' }}>{Object.keys(medicalPortfolio).length}</div>
            <div style={{ fontSize:'11px', color: C.textMuted }}>Staff Medical</div>
          </div>
          {Object.entries(CAT_LABELS).filter(([cat]) => !['staff_medical'].includes(cat)).map(([cat, info]) => {
            const cnt = categoryCounts[cat] || 0
            return (
              <div key={cat} style={{ background: C.bgSecondary, borderRadius:'10px', padding:'12px', border:`1px solid ${C.border}`, textAlign:'center' }}>
                <div style={{ fontSize:'20px', marginBottom:'4px' }}>{info.icon}</div>
                <div style={{ fontSize:'22px', fontWeight:800, color: info.color }}>{cnt}</div>
                <div style={{ fontSize:'11px', color: C.textMuted }}>{info.label}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── MEMBERS TAB ── */}
      {tab === 'members' && (
        <div>
          {/* Shared PCSP/auth docs banner */}
          {(memberPortfolios.shared_docs || []).length > 0 && (
            <div style={{ background:'#EBF2FF', border:'1px solid #CCE0FF', borderRadius:'8px', padding:'12px', marginBottom:'14px' }}>
              <div style={{ fontWeight:700, fontSize:'13px', color:'#1045B8', marginBottom:'8px' }}>📋 Shared Authorization Docs (apply to all SWH members)</div>
              <div style={{ display:'flex', flexDirection:'column', gap:'5px' }}>
                {memberPortfolios.shared_docs.map(f => (
                  <div key={f.filename} style={{ display:'flex', alignItems:'center', gap:'8px', fontSize:'12px', color:'#1045B8' }}>
                    <span>📄</span>
                    <span style={{ fontWeight:600 }}>{f.filename}</span>
                    <span style={{ color:'#4A5568' }}>· {(f.size/1024).toFixed(0)} KB · {f.type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Search + upload info */}
          <div style={{ display:'flex', gap:'8px', marginBottom:'12px', alignItems:'center' }}>
            <input
              value={memberSearch} onChange={e => setMemberSearch(e.target.value)}
              placeholder="Search members..."
              style={{ flex:1, padding:'7px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px',
                background: C.bgSecondary, color: C.text }}
            />
            <div style={{ fontSize:'11px', color: C.textMuted, whiteSpace:'nowrap' }}>
              {filteredMemberPortfolios.length} with individual docs
            </div>
          </div>

          {/* Per-member docs */}
          {filteredMemberPortfolios.length > 0 ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'6px', maxHeight:'320px', overflowY:'auto' }}>
              {filteredMemberPortfolios.map(([name, files]) => (
                <div key={name} style={{ padding:'10px 12px', background: C.bgSecondary, borderRadius:'8px', border:`1px solid ${C.border}` }}>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'5px' }}>
                    <div style={{ fontWeight:600, fontSize:'13px', color: C.text }}>👤 {name}</div>
                    <div style={{ fontSize:'11px', color:'#276749', fontWeight:600 }}>{files.length} doc{files.length!==1?'s':''}</div>
                  </div>
                  {files.map(f => (
                    <div key={f.filename} style={{ fontSize:'11px', color: C.textMuted, marginLeft:'16px' }}>
                      📄 {f.filename} · {(f.size/1024).toFixed(0)} KB
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign:'center', padding:'24px', color: C.textMuted, fontSize:'13px' }}>
              <div style={{ fontSize:'32px', marginBottom:'8px' }}>📂</div>
              {memberSearch ? `No members matching "${memberSearch}"` : 'No individual member docs uploaded yet.'}
              <div style={{ marginTop:'8px', fontSize:'12px' }}>
                Click <strong>Route Emails</strong> to pull PCSP forms + authorization docs from Gmail.
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── STAFF TAB ── */}
      {tab === 'staff' && (
        <div>
          <div style={{ fontSize:'13px', fontWeight:600, color: C.textMid, marginBottom:'10px' }}>🩺 Staff Medical Portfolios</div>
          {Object.keys(medicalPortfolio).length > 0 ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'6px', maxHeight:'360px', overflowY:'auto' }}>
              {Object.entries(medicalPortfolio).map(([staff, files]) => (
                <div key={staff} style={{ display:'flex', alignItems:'center', gap:'10px', padding:'8px 12px', background: C.bgSecondary, borderRadius:'8px', border:`1px solid ${C.border}` }}>
                  <div style={{ fontSize:'20px' }}>👤</div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontWeight:600, fontSize:'13px', color: C.text }}>{staff.replace(/_/g, ' ')}</div>
                    <div style={{ fontSize:'11px', color: C.textMuted }}>{files.map(f => f.filename).join(', ')}</div>
                  </div>
                  <div style={{ fontSize:'11px', color:'#276749', fontWeight:600 }}>{files.length} doc{files.length!==1?'s':''}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign:'center', color: C.textMuted, padding:'24px', fontSize:'13px' }}>
              No staff medical docs yet. Click Route Emails to download from Gmail.
            </div>
          )}
        </div>
      )}

      {/* ── COMPLIANCE TAB ── */}
      {tab === 'compliance' && (
        <div>
          <div style={{ fontSize:'13px', fontWeight:600, color: C.textMid, marginBottom:'12px' }}>🔒 Compliance & Site Visit Documents</div>
          {docs.filter(d => ['compliance_audit','site_visit'].includes(d.category)).length > 0 ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'5px', maxHeight:'360px', overflowY:'auto' }}>
              {docs.filter(d => ['compliance_audit','site_visit'].includes(d.category)).map((f, i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:'10px', padding:'8px 12px', background: C.bgSecondary, borderRadius:'8px', border:`1px solid ${C.border}` }}>
                  <span>{f.category==='compliance_audit' ? '🔒' : '🏛'}</span>
                  <div style={{ flex:1 }}>
                    <div style={{ fontWeight:600, fontSize:'12px', color: C.text }}>{f.filename}</div>
                    <div style={{ fontSize:'10px', color: C.textMuted }}>{f.description} · {(f.size/1024).toFixed(0)} KB</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign:'center', color: C.textMuted, padding:'24px', fontSize:'13px' }}>
              No compliance docs yet. Click Route Emails to pull from Gmail.
            </div>
          )}
        </div>
      )}

      {docs.length === 0 && !loading && tab === 'overview' && (
        <div style={{ textAlign:'center', color: C.textMuted, padding:'30px', fontSize:'13px', marginTop:'8px' }}>
          Vault is empty. Click <strong>📥 Route Emails</strong> to download and organize all documents from Gmail.
        </div>
      )}
    </div>
  )
}

function EDIPanel({ onClose }) {
  const C = useTheme()
  const API = window.REX_API_URL || 'http://localhost:8000'

  const [tab,         setTab]         = useState('upload')   // 'upload' | 'claims' | 'eras' | 'summary'
  const [dragOver,    setDragOver]    = useState(false)
  const [uploading,   setUploading]   = useState(false)
  const [uploadResult,setUploadResult]= useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [claims,      setClaims]      = useState([])
  const [eras,        setEras]        = useState([])
  const [summary,     setSummary]     = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [selected,    setSelected]    = useState(null)   // full detail view

  const loadClaims = () => {
    setLoading(true)
    fetch(`${API}/api/edi/claims`).then(r=>r.json()).then(d=>{ setClaims(d.claims||[]); setLoading(false) }).catch(()=>setLoading(false))
  }
  const loadEras = () => {
    setLoading(true)
    fetch(`${API}/api/edi/remittances`).then(r=>r.json()).then(d=>{ setEras(d.remittances||[]); setLoading(false) }).catch(()=>setLoading(false))
  }
  const loadSummary = () => {
    setLoading(true)
    fetch(`${API}/api/edi/summary`).then(r=>r.json()).then(d=>{ setSummary(d); setLoading(false) }).catch(()=>setLoading(false))
  }

  useEffect(() => {
    if (tab === 'claims')  loadClaims()
    if (tab === 'eras')    loadEras()
    if (tab === 'summary') loadSummary()
  }, [tab])

  const handleFile = async (file) => {
    if (!file) return
    setUploading(true); setUploadResult(null); setUploadError(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch(`${API}/api/edi/upload`, { method:'POST', body:fd })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Upload failed')
      setUploadResult(d)
    } catch(e) {
      setUploadError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const panelW  = Math.min(window.innerWidth - 40, 900)
  const tabBtn  = (id, label) => (
    <button onClick={()=>{ setTab(id); setSelected(null) }} style={{
      padding:'6px 18px', borderRadius:'6px', border:'none', cursor:'pointer', fontSize:'13px', fontWeight:600,
      background: tab===id ? C.blue : C.bgSecondary,
      color:       tab===id ? '#fff' : C.textSecondary,
    }}>{label}</button>
  )

  const dollarColor = (amt) => parseFloat(amt) > 0 ? '#16A34A' : '#DC2626'

  return (
    <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.55)', zIndex:1200, display:'flex', alignItems:'center', justifyContent:'center' }}
         onClick={e=>{ if(e.target===e.currentTarget) onClose() }}>
      <div style={{ width:`${panelW}px`, maxHeight:'90vh', background:C.bg, borderRadius:'16px', display:'flex', flexDirection:'column', overflow:'hidden', boxShadow:'0 8px 40px rgba(0,0,0,0.4)' }}>

        {/* Header */}
        <div style={{ padding:'18px 24px 14px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:'12px' }}>
          <span style={{ fontSize:'22px' }}>📋</span>
          <div style={{ flex:1 }}>
            <div style={{ fontWeight:700, fontSize:'17px', color:C.text }}>EDI Receiver & Interpreter</div>
            <div style={{ fontSize:'12px', color:C.textSecondary }}>837 Claim Submissions · 835 Electronic Remittance Advice</div>
          </div>
          <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'22px', color:C.textSecondary, cursor:'pointer' }}>×</button>
        </div>

        {/* Tabs */}
        <div style={{ padding:'12px 24px 0', display:'flex', gap:'8px', borderBottom:`1px solid ${C.border}` }}>
          {tabBtn('upload',  '⬆️ Upload')}
          {tabBtn('claims',  '📄 Claims (837)')}
          {tabBtn('eras',    '💰 Remittances (835)')}
          {tabBtn('summary', '📊 Revenue Summary')}
        </div>

        {/* Body */}
        <div style={{ flex:1, overflowY:'auto', padding:'20px 24px' }}>

          {/* ── Upload Tab ── */}
          {tab === 'upload' && (
            <div>
              <p style={{ color:C.textSecondary, fontSize:'13px', marginBottom:'16px' }}>
                Drop or select an <strong>837P</strong> (claim submission) or <strong>835</strong> (remittance advice) EDI file.
                REX will auto-detect the type, parse every segment, and give you a plain-English summary with action items.
              </p>

              {/* Drop zone */}
              <div
                onDragOver={e=>{ e.preventDefault(); setDragOver(true) }}
                onDragLeave={()=>setDragOver(false)}
                onDrop={e=>{ e.preventDefault(); setDragOver(false); const f=e.dataTransfer.files[0]; if(f) handleFile(f) }}
                style={{
                  border: `2px dashed ${dragOver ? C.blue : C.border}`,
                  borderRadius:'12px', padding:'40px 20px', textAlign:'center',
                  background: dragOver ? (C.dark ? '#1e2a3a' : '#EFF6FF') : C.bgSecondary,
                  cursor:'pointer', transition:'all .2s',
                }}
                onClick={()=>{ if(!uploading) document.getElementById('edi-file-input').click() }}
              >
                <input id="edi-file-input" type="file" accept="*" style={{ display:'none' }}
                  onChange={e=>{ const f=e.target.files[0]; if(f) handleFile(f); e.target.value='' }} />
                {uploading
                  ? <div style={{ color:C.blue, fontSize:'16px' }}>⏳ Parsing EDI file…</div>
                  : <>
                      <div style={{ fontSize:'36px', marginBottom:'8px' }}>📂</div>
                      <div style={{ fontWeight:600, color:C.text }}>Drop your 837 or 835 EDI file here</div>
                      <div style={{ fontSize:'12px', color:C.textSecondary, marginTop:'4px' }}>or click to browse — any file name or extension works</div>
                    </>
                }
              </div>

              {/* Error */}
              {uploadError && (
                <div style={{ marginTop:'16px', padding:'12px 16px', background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'8px', color:'#B91C1C', fontSize:'13px' }}>
                  ❌ {uploadError}
                </div>
              )}

              {/* Result */}
              {uploadResult && (
                <div style={{ marginTop:'16px' }}>
                  <div style={{ padding:'14px 16px', background: uploadResult.type==='835' ? '#F0FDF4' : '#EFF6FF',
                    border:`1px solid ${uploadResult.type==='835' ? '#86EFAC' : '#BFDBFE'}`, borderRadius:'10px', marginBottom:'12px' }}>
                    <div style={{ fontWeight:700, fontSize:'14px', marginBottom:'6px', color: uploadResult.type==='835' ? '#15803D' : '#1D4ED8' }}>
                      {uploadResult.type==='835' ? '💰 835 ERA Received' : '📄 837 Claims Received'} — {uploadResult.filename}
                    </div>
                    <div style={{ fontSize:'13px', color:'#374151', whiteSpace:'pre-wrap', lineHeight:1.6 }}>
                      {uploadResult.summary}
                    </div>
                  </div>

                  {uploadResult.action_items?.length > 0 && (
                    <div style={{ background:'#FFFBEB', border:'1px solid #FCD34D', borderRadius:'10px', padding:'14px 16px' }}>
                      <div style={{ fontWeight:700, fontSize:'13px', color:'#92400E', marginBottom:'8px' }}>⚠️ Action Items</div>
                      {uploadResult.action_items.map((item,i) => (
                        <div key={i} style={{ fontSize:'13px', color:'#78350F', padding:'3px 0', borderBottom: i < uploadResult.action_items.length-1 ? '1px solid #FDE68A' : 'none' }}>
                          {i+1}. {item}
                        </div>
                      ))}
                    </div>
                  )}

                  {uploadResult.denial_breakdown && Object.keys(uploadResult.denial_breakdown).length > 0 && (
                    <div style={{ marginTop:'12px', background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'10px', padding:'14px 16px' }}>
                      <div style={{ fontWeight:700, fontSize:'13px', color:'#B91C1C', marginBottom:'8px' }}>🚫 Denial Reasons</div>
                      {Object.entries(uploadResult.denial_breakdown).map(([code, cnt]) => (
                        <div key={code} style={{ fontSize:'12px', color:'#991B1B', padding:'2px 0' }}>{code}: {cnt} claim{cnt>1?'s':''}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Claims Tab ── */}
          {tab === 'claims' && (
            <div>
              {loading && <div style={{ color:C.textSecondary, fontSize:'13px' }}>Loading claims…</div>}
              {!loading && claims.length === 0 && (
                <div style={{ textAlign:'center', color:C.textSecondary, fontSize:'13px', marginTop:'40px' }}>
                  No 837 claim files uploaded yet. Use the Upload tab to add one.
                </div>
              )}
              {claims.map(c => (
                <div key={c.file_id} style={{ border:`1px solid ${C.border}`, borderRadius:'10px', padding:'14px 16px', marginBottom:'10px',
                  background: selected?.file_id===c.file_id ? (C.dark ? '#1e2a3a' : '#EFF6FF') : C.bgSecondary, cursor:'pointer' }}
                  onClick={()=>setSelected(selected?.file_id===c.file_id ? null : c)}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <div>
                      <span style={{ fontWeight:700, color:C.text, fontSize:'14px' }}>📄 {c.filename}</span>
                      <span style={{ marginLeft:'10px', fontSize:'11px', color:C.textSecondary }}>{c.uploaded_at?.slice(0,10)}</span>
                    </div>
                    <div style={{ fontWeight:700, color:'#1D4ED8', fontSize:'14px' }}>
                      ${(c.interpreted?.total_billed||0).toLocaleString('en-US',{minimumFractionDigits:2})}
                    </div>
                  </div>
                  <div style={{ fontSize:'12px', color:C.textSecondary, marginTop:'4px' }}>
                    {c.interpreted?.claim_count||0} claim{c.interpreted?.claim_count!==1?'s':''} · ID: {c.file_id}
                  </div>
                  {selected?.file_id===c.file_id && (
                    <div style={{ marginTop:'12px', fontSize:'13px', color:C.text, whiteSpace:'pre-wrap', lineHeight:1.6,
                      borderTop:`1px solid ${C.border}`, paddingTop:'10px' }}>
                      {c.interpreted?.plain_english || 'No summary available.'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── ERAs Tab ── */}
          {tab === 'eras' && (
            <div>
              {loading && <div style={{ color:C.textSecondary, fontSize:'13px' }}>Loading remittances…</div>}
              {!loading && eras.length === 0 && (
                <div style={{ textAlign:'center', color:C.textSecondary, fontSize:'13px', marginTop:'40px' }}>
                  No 835 ERA files uploaded yet. Use the Upload tab to add one.
                </div>
              )}
              {eras.map(e => {
                const interp = e.interpreted || {}
                return (
                  <div key={e.file_id} style={{ border:`1px solid ${C.border}`, borderRadius:'10px', padding:'14px 16px', marginBottom:'10px',
                    background: selected?.file_id===e.file_id ? (C.dark ? '#1a2e1a' : '#F0FDF4') : C.bgSecondary, cursor:'pointer' }}
                    onClick={()=>setSelected(selected?.file_id===e.file_id ? null : e)}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <div>
                        <span style={{ fontWeight:700, color:C.text, fontSize:'14px' }}>💰 {e.filename}</span>
                        <span style={{ marginLeft:'10px', fontSize:'11px', color:C.textSecondary }}>{e.uploaded_at?.slice(0,10)}</span>
                      </div>
                      <div style={{ textAlign:'right' }}>
                        <div style={{ fontWeight:700, color:'#16A34A', fontSize:'14px' }}>${(interp.total_paid||0).toLocaleString('en-US',{minimumFractionDigits:2})} paid</div>
                        {interp.total_denied > 0 && <div style={{ fontWeight:600, color:'#DC2626', fontSize:'12px' }}>${(interp.total_denied||0).toLocaleString('en-US',{minimumFractionDigits:2})} denied</div>}
                      </div>
                    </div>
                    <div style={{ fontSize:'12px', color:C.textSecondary, marginTop:'4px' }}>
                      {interp.payment_count||0} payment{interp.payment_count!==1?'s':''} · Rate: {interp.reimbursement_rate||0}% · ID: {e.file_id}
                    </div>
                    {selected?.file_id===e.file_id && (
                      <div style={{ marginTop:'12px', borderTop:`1px solid ${C.border}`, paddingTop:'10px' }}>
                        <div style={{ fontSize:'13px', color:C.text, whiteSpace:'pre-wrap', lineHeight:1.6, marginBottom:'10px' }}>
                          {interp.plain_english || 'No summary available.'}
                        </div>
                        {interp.action_items?.length > 0 && (
                          <div style={{ background:'#FFFBEB', border:'1px solid #FCD34D', borderRadius:'8px', padding:'10px 12px' }}>
                            <div style={{ fontWeight:700, fontSize:'12px', color:'#92400E', marginBottom:'6px' }}>⚠️ Action Items</div>
                            {interp.action_items.map((item,i) => (
                              <div key={i} style={{ fontSize:'12px', color:'#78350F', padding:'2px 0' }}>{i+1}. {item}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* ── Summary Tab ── */}
          {tab === 'summary' && (
            <div>
              {loading && <div style={{ color:C.textSecondary, fontSize:'13px' }}>Loading revenue summary…</div>}
              {!loading && summary && (
                <>
                  {/* KPI cards */}
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:'12px', marginBottom:'20px' }}>
                    {[
                      { label:'Total Billed', value:`$${(summary.total_billed||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#1D4ED8', icon:'📋' },
                      { label:'Total Paid',   value:`$${(summary.total_paid||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#16A34A', icon:'✅' },
                      { label:'Total Denied', value:`$${(summary.total_denied||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#DC2626', icon:'🚫' },
                      { label:'Outstanding',  value:`$${(summary.outstanding||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#D97706', icon:'⏳' },
                      { label:'Reimbursement Rate', value:`${summary.reimbursement_rate||0}%`, color: (summary.reimbursement_rate||0) >= 80 ? '#16A34A' : '#DC2626', icon:'📈' },
                      { label:'Files Processed', value:`${summary.files_processed||0}`, color:C.textSecondary, icon:'📁' },
                    ].map(kpi => (
                      <div key={kpi.label} style={{ background:C.bgSecondary, border:`1px solid ${C.border}`, borderRadius:'10px', padding:'14px 16px' }}>
                        <div style={{ fontSize:'18px', marginBottom:'4px' }}>{kpi.icon}</div>
                        <div style={{ fontSize:'11px', color:C.textSecondary, textTransform:'uppercase', letterSpacing:'0.5px' }}>{kpi.label}</div>
                        <div style={{ fontWeight:700, fontSize:'18px', color:kpi.color, marginTop:'2px' }}>{kpi.value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Denial reasons */}
                  {summary.denial_reasons && Object.keys(summary.denial_reasons).length > 0 && (
                    <div style={{ background:'#FEF2F2', border:'1px solid #FCA5A5', borderRadius:'10px', padding:'16px' }}>
                      <div style={{ fontWeight:700, fontSize:'14px', color:'#B91C1C', marginBottom:'10px' }}>🚫 Top Denial Reasons</div>
                      {Object.entries(summary.denial_reasons).sort((a,b)=>b[1]-a[1]).map(([reason, count]) => (
                        <div key={reason} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:`1px solid #FEE2E2`, fontSize:'13px' }}>
                          <span style={{ color:'#991B1B' }}>{reason}</span>
                          <span style={{ fontWeight:700, color:'#B91C1C' }}>{count} claim{count>1?'s':''}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {summary.files_processed === 0 && (
                    <div style={{ textAlign:'center', color:C.textSecondary, fontSize:'13px', marginTop:'20px' }}>
                      No EDI files uploaded yet. Upload 837 or 835 files to see revenue analytics.
                    </div>
                  )}
                </>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

// ── Telegram Feed Panel ───────────────────────────────────────────────────────
function TelegramFeedPanel({ onClose }) {
  const C = useTheme()
  const [config,   setConfig]   = useState(null)
  const [messages, setMessages] = useState([])
  const [schedule, setSchedule] = useState('')
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState(null)
  const [tab,      setTab]      = useState('feed')

  useEffect(() => {
    fetch(`${API}/api/telegram/config`).then(r=>r.json()).then(setConfig).catch(()=>{})
    fetch(`${API}/api/telegram/messages?limit=20`).then(r=>r.json()).then(d => setMessages(d.messages || [])).catch(()=>{})
    fetch(`${API}/api/telegram/schedule`).then(r=>r.json()).then(d => setSchedule(d.summary || '')).catch(()=>{})
  }, [])

  const doFetch = async () => {
    setFetching(true); setFetchMsg(null)
    try {
      const d = await fetch(`${API}/api/telegram/fetch`,{method:'POST'}).then(r=>r.json())
      setFetchMsg(d.ok ? `✅ Fetched ${d.new} new message(s)` : `❌ ${d.error}`)
      if (d.ok) {
        fetch(`${API}/api/telegram/messages?limit=20`).then(r=>r.json()).then(d2 => setMessages(d2.messages || [])).catch(()=>{})
        fetch(`${API}/api/telegram/schedule`).then(r=>r.json()).then(d2 => setSchedule(d2.summary || '')).catch(()=>{})
      }
    } catch(e) { setFetchMsg(`❌ ${e.message}`) }
    setFetching(false)
  }

  const PANEL = {
    position:'fixed', top:0, right:0, bottom:0, width:'420px', maxWidth:'100vw',
    background:C.white, borderLeft:`1px solid ${C.border}`,
    boxShadow:'-4px 0 32px rgba(0,0,0,0.12)',
    zIndex:800, display:'flex', flexDirection:'column',
  }

  return (
    <div style={PANEL}>
      <div style={{ padding:'16px 20px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', gap:'12px', background:`linear-gradient(135deg,#229ED918,${C.white})` }}>
        <span style={{ fontSize:'24px' }}>✈️</span>
        <div style={{ flex:1 }}>
          <div style={{ fontWeight:700, fontSize:'16px', color:C.text }}>GOJ Telegram Feed</div>
          <div style={{ fontSize:'12px', color: config?.configured ? '#229ED9' : C.error }}>
            {config?.configured ? `Watching: ${config.channel}` : 'Not configured — paste channel link'}
          </div>
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', fontSize:'20px', color:C.textMuted, cursor:'pointer' }}>✕</button>
      </div>

      <div style={{ display:'flex', gap:'2px', padding:'8px 16px', borderBottom:`1px solid ${C.border}`, flexShrink:0 }}>
        {['feed','schedule','setup'].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding:'6px 14px', borderRadius:'8px', border:'none', cursor:'pointer', fontSize:'13px', fontWeight: tab===t ? 700 : 400,
            background: tab===t ? '#229ED9' : 'transparent', color: tab===t ? '#fff' : C.textMid,
          }}>{t === 'feed' ? '📡 Feed' : t === 'schedule' ? '📅 Schedules' : '⚙ Setup'}</button>
        ))}
      </div>

      <div style={{ flex:1, overflowY:'auto', padding:'16px' }}>
        {tab === 'feed' && (
          <>
            <div style={{ display:'flex', gap:'8px', marginBottom:'12px' }}>
              <button onClick={doFetch} disabled={fetching} style={{
                flex:1, padding:'9px', borderRadius:'8px', background:'#229ED9', color:'#fff', border:'none', fontSize:'13px', cursor:'pointer',
              }}>{fetching ? '⏳ Fetching…' : '🔄 Fetch Latest'}</button>
            </div>
            {fetchMsg && <div style={{ fontSize:'12px', marginBottom:'10px', color: fetchMsg.startsWith('✅') ? C.success : C.error }}>{fetchMsg}</div>}
            {!config?.configured && (
              <div style={{ padding:'14px', background:'#E8F4FD', borderRadius:'10px', fontSize:'13px', color:'#1A5276', marginBottom:'12px' }}>
                ℹ️ Go to the <strong>Setup</strong> tab to connect your GOJ channel. Paste the channel link (e.g. <code>@goj_ops</code>) and your bot token.
              </div>
            )}
            {messages.length === 0
              ? <div style={{ fontSize:'13px', color:C.textMuted, padding:'12px 0' }}>No cached messages. Click Fetch Latest above.</div>
              : messages.map((m,i) => (
                  <div key={i} style={{ padding:'10px 12px', marginBottom:'6px', background:C.bgSecondary, borderRadius:'8px', borderLeft:'3px solid #229ED9' }}>
                    <div style={{ fontSize:'11px', color:C.textMuted, marginBottom:'4px' }}>{m.from} · {m.date?.slice(0,16)}</div>
                    <div style={{ fontSize:'13px', color:C.text, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>{m.text?.slice(0,400)}</div>
                  </div>
                ))
            }
          </>
        )}

        {tab === 'schedule' && (
          <div>
            <div style={{ fontSize:'13px', color:C.textMid, whiteSpace:'pre-wrap' }}>{schedule || 'No schedule data found. Fetch messages first.'}</div>
          </div>
        )}

        {tab === 'setup' && (
          <TelegramSetupTab config={config} setConfig={setConfig} />
        )}
      </div>
    </div>
  )
}

function TelegramSetupTab({ config, setConfig }) {
  const C = useTheme()
  const [channel,   setChannel]  = useState(config?.channel || '')
  const [botToken,  setBotToken] = useState('')
  const [mode,      setMode]     = useState(config?.mode || 'bot')
  const [saving,    setSaving]   = useState(false)
  const [saved,     setSaved]    = useState(false)

  const save = async () => {
    setSaving(true); setSaved(false)
    const body = { channel, mode }
    if (botToken) body.bot_token = botToken
    try {
      await fetch(`${API}/api/telegram/config`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) })
      setConfig(c => ({ ...c, channel, mode, configured: !!channel }))
      setSaved(true)
    } catch {}
    setSaving(false)
  }

  return (
    <div>
      <div style={{ fontSize:'13px', color:C.textMid, marginBottom:'16px' }}>
        Paste your GOJ Telegram channel link so REX can read schedules and announcements.
      </div>

      <label style={{ fontSize:'12px', fontWeight:600, color:C.textMid }}>Channel Username or Link</label>
      <input value={channel} onChange={e=>setChannel(e.target.value)} placeholder="@goj_operations  or  -100123456789"
        style={{ width:'100%', padding:'9px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px', marginTop:'4px', marginBottom:'12px', background:C.bgSecondary, color:C.text, boxSizing:'border-box' }} />

      <label style={{ fontSize:'12px', fontWeight:600, color:C.textMid }}>Mode</label>
      <select value={mode} onChange={e=>setMode(e.target.value)}
        style={{ width:'100%', padding:'9px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px', marginTop:'4px', marginBottom:'12px', background:C.bgSecondary, color:C.text }}>
        <option value="bot">Bot mode (public channels)</option>
        <option value="user">User mode (private channels — needs Telethon)</option>
      </select>

      <label style={{ fontSize:'12px', fontWeight:600, color:C.textMid }}>Bot Token (for bot mode)</label>
      <input value={botToken} onChange={e=>setBotToken(e.target.value)} type="password"
        placeholder="Paste your Telegram bot token here"
        style={{ width:'100%', padding:'9px 12px', borderRadius:'8px', border:`1px solid ${C.border}`, fontSize:'13px', marginTop:'4px', marginBottom:'16px', background:C.bgSecondary, color:C.text, boxSizing:'border-box' }} />

      <div style={{ fontSize:'12px', color:C.textMuted, background:C.bgSecondary, borderRadius:'8px', padding:'10px 12px', marginBottom:'16px' }}>
        <strong>Bot mode setup:</strong> Add the REX bot as admin to your channel, then click Save. The bot will receive all new channel posts going forward.
      </div>

      <button onClick={save} disabled={saving} style={{
        width:'100%', padding:'11px', borderRadius:'8px', border:'none',
        background:'#229ED9', color:'#fff', fontSize:'14px', fontWeight:600, cursor:'pointer',
      }}>{saving ? '⏳ Saving…' : '💾 Save Configuration'}</button>
      {saved && <div style={{ marginTop:'10px', fontSize:'13px', color:C.success }}>✅ Saved! Click Fetch Latest in the Feed tab to pull messages.</div>}
    </div>
  )
}

export default function App() {
  const isMobile = useIsMobile()
  const [appearance, setAppearance]   = useState(loadAppearance)
  // Auto-restore session from localStorage (Remember me) or sessionStorage (current tab)
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const u = sessionStorage.getItem('rex-user') || localStorage.getItem('rex-user')
      return u ? JSON.parse(u) : null
    } catch { return null }
  })
  const [locked, setLocked] = useState(() => {
    // If a saved token exists in either store, start unlocked (token verified on first API call)
    const token = sessionStorage.getItem('rex-token') || localStorage.getItem('rex-token')
    return !token
  })
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [messages, setMessages]       = useState([])
  const [input, setInput]             = useState('')
  const [secure, setSecure]           = useState(false)
  const [models, setModels]           = useState([])
  const [selectedModel, setSelectedModel] = useState('ollama/llama3')
  const [streaming, setStreaming]     = useState(false)
  const [journeys, setJourneys]       = useState([])
  const [currentJourneyId, setCurrentJourneyId] = useState(null)
  const [health, setHealth]           = useState(null)
  const [showSettings, setShowSettings]     = useState(false)
  const [showGmail,    setShowGmail]         = useState(false)
  const [showUpload,   setShowUpload]        = useState(false)
  const [showTelegram, setShowTelegram]      = useState(false)
  const [wsConnected,  setWsConnected]       = useState(false)
  const [showSideProject, setShowSideProject] = useState(false)
  const [showCalendar,    setShowCalendar]    = useState(false)
  const [showAudit,       setShowAudit]       = useState(false)
  const [showEDI,         setShowEDI]         = useState(false)
  const [showStaff,            setShowStaff]            = useState(false)
  const [showAttendance,       setShowAttendance]        = useState(false)
  const [showGOJ,              setShowGOJ]               = useState(false)
  const [showDocumentVault,    setShowDocumentVault]     = useState(false)
  const [showEmployeePerms,    setShowEmployeePerms]     = useState(false)
  const [pendingPdfs,  setPendingPdfs]        = useState([])

  // Poll for pending PDF emails every 2 minutes
  useEffect(() => {
    const fetchPdfs = () => {
      fetch(`${API}/api/chairman/pending-pdfs`)
        .then(r => r.ok ? r.json() : { pending: [] })
        .catch(() => ({ pending: [] }))
        .then(d => setPendingPdfs(d.pending || []))
    }
    fetchPdfs()
    const id = setInterval(fetchPdfs, 120000)
    return () => clearInterval(id)
  }, [])
  // Persist Rexxie mode across reconnects & page reloads — reads from sessionStorage on mount
  const [rexxieMode, _setRexxieMode]  = useState(() => sessionStorage.getItem('rex-rexxie-mode') === 'true')
  const setRexxieMode = (val) => {
    sessionStorage.setItem('rex-rexxie-mode', String(val))
    _setRexxieMode(val)
  }
  const [eggPhase, setEggPhase]       = useState(1) // 1=cracked (empty chat), 2=hatched (conversation live)

  // Compute live theme (shadows module-level C so every reference in this component uses current theme)
  const C = computeTheme(appearance)

  // ── Role helpers ─────────────────────────────────────────────────────────────
  const PRIVILEGED_ROLES = ['chairman', 'admin', 'director']
  const isPrivileged = (user) => user && PRIVILEGED_ROLES.includes((user.role || '').toLowerCase())
  const canAccessPanel = (panel) => {
    if (!currentUser) return false
    if (isPrivileged(currentUser)) return true
    return (currentUser.panel_permissions || []).includes(panel)
  }
  // Auth token helper — for protected API calls
  const getAuthToken = () =>
    sessionStorage.getItem('rex-token') || localStorage.getItem('rex-token') || ''
  const authHeaders = () => ({ 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' })

  const wsRef        = useRef(null)
  const bottomRef    = useRef(null)
  const streamBufRef = useRef('')
  const inputRef     = useRef(null)

  // WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    // Keepalive ping every 25s — prevents OS/browser from killing idle WS
    let pingTimer = null
    ws.onopen = () => {
      setWsConnected(true)
      pingTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
      }, 25000)
      // Request authoritative state from backend immediately on every connect/reconnect
      // so the frontend never shows the wrong mode
      ws.send(JSON.stringify({ type: 'sync_state' }))
    }
    ws.onclose = () => {
      clearInterval(pingTimer)
      setWsConnected(false)
      setTimeout(connect, 3000)
    }
    ws.onerror = () => setWsConnected(false)
    ws.onmessage = ({ data }) => {
      const msg = JSON.parse(data)
      switch (msg.type) {
        case 'init':
          setCurrentJourneyId(msg.journey_id)
          setSecure(msg.secure_mode)
          // Restore prior conversation if server recovered a recent session
          if (msg.resumed && msg.history?.length) {
            setMessages(msg.history.map((m, i) => ({
              id: `resumed_${i}`,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp || new Date().toISOString(),
            })))
          }
          break
        case 'stream_start':
          streamBufRef.current = ''
          setStreaming(true)
          setMessages(p => [...p, { id: msg.msg_id+'_r', role:'assistant', content:'', streaming:true, model:msg.model, secure:msg.secure, timestamp:new Date().toISOString() }])
          break
        case 'chunk':
          streamBufRef.current += msg.content
          setMessages(p => p.map(m => m.streaming ? { ...m, content:streamBufRef.current } : m))
          break
        case 'stream_end':
          setStreaming(false)
          setMessages(p => p.map(m => m.streaming ? { ...m, content:msg.display_content, streaming:false, phi_detected:msg.phi_detected, id:msg.resp_id } : m))
          // Sync Rexxie mode from backend's authoritative state (not the model tag, which is
          // 'rexxie-engine' even for "back to rex" confirmations — that was the switching bug)
          if (typeof msg.rexxie_active === 'boolean') setRexxieMode(msg.rexxie_active)
          loadJourneys()
          break
        case 'state_sync':
          // Backend's authoritative state — sent on connect/reconnect and on request
          if (typeof msg.rexxie_active === 'boolean') setRexxieMode(msg.rexxie_active)
          break
        case 'model_set':
          setSelectedModel(msg.model)
          break
        case 'secure_mode_set':
          setSecure(msg.secure_mode)
          break
        case 'error':
          setStreaming(false)
          setMessages(p => [...p, { id:Date.now().toString(), role:'assistant', content:`⚠️ ${msg.message}`, timestamp:new Date().toISOString() }])
          break
      }
    }
  }, [])

  const loadModels = async () => {
    try {
      const d = await fetch(`${API}/api/models`).then(r => r.json())
      setModels(d.models || [])
      const hasOllama = d.ollama_running && (d.models || []).some(m => m.local && m.available)
      const hasAnthropic = (d.models || []).find(m => m.provider === 'anthropic')?.available
      if (hasAnthropic) setSelectedModel('anthropic/claude-sonnet-4-5')
      else if (hasOllama) setSelectedModel('ollama/llama3')
    } catch {}
  }

  const loadJourneys = async () => {
    try { const d = await fetch(`${API}/api/journeys`).then(r => r.json()); setJourneys(d.journeys || []) } catch {}
  }

  const loadHealth = async () => {
    try { const d = await fetch(`${API}/api/health`).then(r => r.json()); setHealth(d) } catch {}
  }

  const loadJourney = async id => {
    try {
      const d = await fetch(`${API}/api/journeys/${id}`).then(r => r.json())
      setMessages(d.messages?.map(m => ({ id:m.id, role:m.role, content:m.content, timestamp:m.timestamp, phi_detected:m.phi_detected, secure:m.secure, model:m.model })) || [])
      setCurrentJourneyId(id)
    } catch {}
  }

  useEffect(() => {
    loadHealth(); loadModels(); loadJourneys(); connect()
    return () => wsRef.current?.close()
  }, [connect])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  // Hatch the egg on first assistant response
  useEffect(() => {
    if (eggPhase < 2 && messages.some(m => m.role === 'assistant' && !m.streaming)) {
      setEggPhase(2)
    }
  }, [messages, eggPhase])

  const send = () => {
    const text = input.trim()
    if (!text || streaming || wsRef.current?.readyState !== WebSocket.OPEN) return
    setMessages(p => [...p, { id:Date.now().toString(), role:'user', content:text, timestamp:new Date().toISOString(), secure, phi_detected:false }])
    setInput('')
    wsRef.current.send(JSON.stringify({ type:'message', content:text, model:selectedModel }))
    if (inputRef.current) inputRef.current.style.height = 'auto'
  }

  const toggleSecure = () => {
    const v = !secure; setSecure(v)
    wsRef.current?.send(JSON.stringify({ type:'set_secure_mode', enabled:v }))
  }

  const changeModel = id => {
    setSelectedModel(id)
    wsRef.current?.send(JSON.stringify({ type:'set_model', model:id }))
  }

  const newChat = () => {
    // Tell the backend to clear the session cache so the new chat starts fresh
    wsRef.current?.send(JSON.stringify({ type: 'clear_session_cache' }))
    wsRef.current?.close()
    setMessages([]); setCurrentJourneyId(null); setRexxieMode(false); setEggPhase(1)
    setTimeout(connect, 300)
  }

  const toggleRexxie = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const next = !rexxieMode
    setRexxieMode(next)
    // Send the natural-language command — the backend detects it and rebuilds the prompt
    wsRef.current.send(JSON.stringify({
      type: 'message',
      content: next ? 'hey rexxie' : 'back to rex',
      model: selectedModel,
    }))
  }

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <ThemeCtx.Provider value={C}>
    <div style={{ fontSize: appearance.fontSize + 'px', background: C.bg, minHeight:'100dvh', color: C.text }}>
      <style>{`
        @keyframes fadeIn  { from { opacity:0 } to { opacity:1 } }
        @keyframes fadeOut { from { opacity:1 } to { opacity:0 } }
        @keyframes glow    { 0%,100%{ box-shadow:0 0 0 0 rgba(0,102,255,0.3) } 50%{ box-shadow:0 0 0 10px rgba(0,102,255,0) } }
        @keyframes pulse   { 0%,100%{ opacity:0.3; transform:scale(0.9) } 50%{ opacity:1; transform:scale(1.1) } }
        @keyframes slideUp { from{ opacity:0; transform:translateY(8px) } to{ opacity:1; transform:translateY(0) } }
        @keyframes wobble    { 0%{ transform:rotate(0deg) } 20%{ transform:rotate(-8deg) } 40%{ transform:rotate(8deg) } 60%{ transform:rotate(-5deg) } 80%{ transform:rotate(5deg) } 100%{ transform:rotate(0deg) } }
        @keyframes spin      { to { transform:rotate(360deg) } }
        @keyframes dinoWiggle{ 0%,100%{ transform:scale(1) rotate(0deg) } 25%{ transform:scale(1.12) rotate(-6deg) } 75%{ transform:scale(1.12) rotate(6deg) } }
        * { box-sizing:border-box; }
        button { border:none; background:none; cursor:pointer; }
        textarea { border:none; outline:none; font-family:inherit; }
        .prose p { margin:0 0 8px } .prose p:last-child { margin:0 }
        .prose pre { background:${C.bgSecondary}; padding:12px; border-radius:8px; overflow-x:auto; font-size:13px; margin:8px 0; color:${C.text} }
        .prose code { background:${C.bgSecondary}; padding:1px 5px; border-radius:4px; font-size:13px; color:${C.text} }
        .prose pre code { background:none; padding:0 }
        .prose ul,.prose ol { padding-left:20px; margin:6px 0 }
        ::-webkit-scrollbar { width:4px } ::-webkit-scrollbar-track { background:transparent } ::-webkit-scrollbar-thumb { background:${C.border}; border-radius:4px }
      `}</style>

      {locked && <LockScreen onUnlock={(user) => { setCurrentUser(user); setLocked(false) }} />}

      {/* Mobile sidebar overlay */}
      {isMobile && sidebarOpen && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.35)', zIndex:499 }}
             onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      {(!isMobile || sidebarOpen) && (
        <Sidebar
          journeys={journeys}
          currentId={currentJourneyId}
          onSelect={loadJourney}
          onNew={newChat}
          onClose={() => setSidebarOpen(false)}
          eggPhase={eggPhase}
          rexxieMode={rexxieMode}
          onToggleRexxie={toggleRexxie}
          toggleDisabled={streaming || !wsConnected}
        />
      )}

      {/* Main */}
      <div style={{
        display:'flex', flexDirection:'column',
        height:'100dvh',
        marginLeft: isMobile ? 0 : '240px',
        background:C.bg,
        overflow:'hidden',
      }}>
        {/* Top bar */}
        <div style={{
          padding: isMobile ? '10px 12px' : '10px 18px',
          background:C.white,
          borderBottom:`1px solid ${secure ? 'rgba(16,69,184,0.2)' : C.border}`,
          display:'flex', alignItems:'center', gap:'8px',
          flexShrink:0,
          boxShadow:'0 1px 4px rgba(0,0,0,0.04)',
        }}>
          {isMobile && (
            <button onClick={() => setSidebarOpen(true)} style={{
              width:'38px', height:'38px', borderRadius:'10px',
              background:C.bgSecondary, border:`1px solid ${C.border}`,
              fontSize:'18px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
            }}>☰</button>
          )}

          <ModelSelector models={models} selected={selectedModel} onSelect={changeModel} />
          <div style={{ flex:1 }} />
          <SecureToggle secure={secure} onToggle={toggleSecure} />

          {/* Telegram / GOJ Feed button — chairman or employees with telegram permission */}
          {canAccessPanel('telegram') && (
            <button onClick={() => { setShowTelegram(s=>!s); setShowGmail(false); setShowUpload(false) }}
              title="GOJ Telegram Feed"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showTelegram ? '#229ED9' : C.bgSecondary,
                border:`1px solid ${showTelegram ? '#229ED9' : C.border}`,
                color: showTelegram ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>✈️</button>
          )}

          {/* Upload / Documents button — chairman or employees with upload/documents permission */}
          {canAccessPanel('upload') && (
            <button onClick={() => { setShowUpload(s=>!s); setShowGmail(false); setShowTelegram(false) }}
              title="Documents & Uploads"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showUpload ? C.blue : C.bgSecondary,
                border:`1px solid ${showUpload ? C.blue : C.border}`,
                color: showUpload ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>📁</button>
          )}

          {/* Gmail button — chairman or employees with gmail permission */}
          {canAccessPanel('gmail') && (
            <button onClick={() => { setShowGmail(s=>!s); setShowUpload(false); setShowTelegram(false) }}
              title="Gmail"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showGmail ? '#EA4335' : C.bgSecondary,
                border:`1px solid ${showGmail ? '#EA4335' : C.border}`,
                color: showGmail ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>📧</button>
          )}

          {/* Calendar / Schedule — with PDF badge — chairman or employees with calendar permission */}
          {canAccessPanel('calendar') && (
            <div style={{ position:'relative', flexShrink:0 }}>
              <button onClick={() => { setShowCalendar(s=>!s); setShowAudit(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false) }}
                title="Schedule & Calendar"
                style={{
                  width:'38px', height:'38px', borderRadius:'50%',
                  background: showCalendar ? C.blue : C.bgSecondary,
                  border:`1px solid ${showCalendar ? C.blue : C.border}`,
                  color: showCalendar ? '#fff' : C.textMid,
                  fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center',
                  transition:'all 0.2s',
                }}>📅</button>
              {pendingPdfs.length > 0 && (
                <div style={{
                  position:'absolute', top:'-4px', right:'-4px',
                  background:'#E53E3E', color:'#fff', borderRadius:'50%',
                  width:'16px', height:'16px', fontSize:'9px', fontWeight:700,
                  display:'flex', alignItems:'center', justifyContent:'center',
                  border:'2px solid #fff', pointerEvents:'none',
                }}>{pendingPdfs.length}</div>
              )}
            </div>
          )}

          {/* Chairman Audit Trail — chairman only */}
          {isPrivileged(currentUser) && (
            <button onClick={() => { setShowAudit(s=>!s); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEDI(false) }}
              title="Chairman Audit Trail"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showAudit ? '#1045B8' : C.bgSecondary,
                border:`1px solid ${showAudit ? '#1045B8' : C.border}`,
                color: showAudit ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>👁</button>
          )}

          {/* Staff Compliance — Chairman + Admin/Director only */}
          {isPrivileged(currentUser) && (
            <button onClick={() => { setShowStaff(s=>!s); setShowAttendance(false); setShowEDI(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEmployeePerms(false) }}
              title="Staff Compliance & Medicals (Restricted)"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showStaff ? '#276749' : C.bgSecondary,
                border:`1px solid ${showStaff ? '#276749' : C.border}`,
                color: showStaff ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>👥</button>
          )}

          {/* Client Attendance — Chairman or employees with attendance permission */}
          {canAccessPanel('attendance') && (
            <button onClick={() => { setShowAttendance(s=>!s); setShowStaff(false); setShowEDI(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEmployeePerms(false) }}
              title="Client Attendance Sheet"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showAttendance ? '#2B6CB0' : C.bgSecondary,
                border:`1px solid ${showAttendance ? '#2B6CB0' : C.border}`,
                color: showAttendance ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>📋</button>
          )}

          {/* GOJ Members & Stats — Chairman/Director */}
          {isPrivileged(currentUser) && (
            <button onClick={() => { setShowGOJ(s=>!s); setShowAttendance(false); setShowStaff(false); setShowEDI(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEmployeePerms(false); setShowDocumentVault(false) }}
              title="GOJ Members & Stats"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showGOJ ? '#276749' : C.bgSecondary,
                border:`1px solid ${showGOJ ? '#276749' : C.border}`,
                color: showGOJ ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>🏥</button>
          )}

          {/* Document Vault — Chairman/Director */}
          {isPrivileged(currentUser) && (
            <button onClick={() => { setShowDocumentVault(s=>!s); setShowGOJ(false); setShowAttendance(false); setShowStaff(false); setShowEDI(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEmployeePerms(false) }}
              title="Document Vault"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showDocumentVault ? '#C05621' : C.bgSecondary,
                border:`1px solid ${showDocumentVault ? '#C05621' : C.border}`,
                color: showDocumentVault ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>📁</button>
          )}

          {/* Manage Employee Access — Chairman only */}
          {currentUser?.role === 'chairman' && (
            <button onClick={() => { setShowEmployeePerms(s=>!s); setShowStaff(false); setShowAttendance(false); setShowEDI(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowGOJ(false); setShowDocumentVault(false) }}
              title="Manage Employee Access"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showEmployeePerms ? '#6B46C1' : C.bgSecondary,
                border:`1px solid ${showEmployeePerms ? '#6B46C1' : C.border}`,
                color: showEmployeePerms ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>🔑</button>
          )}

          {/* EDI 837/835 Receiver — Chairman or employees with edi permission */}
          {canAccessPanel('edi') && (
            <button onClick={() => { setShowEDI(s=>!s); setShowAttendance(false); setShowStaff(false); setShowAudit(false); setShowCalendar(false); setShowGmail(false); setShowUpload(false); setShowTelegram(false); setShowEmployeePerms(false) }}
              title="EDI Receiver — 837 Claims / 835 ERA"
              style={{
                width:'38px', height:'38px', borderRadius:'50%',
                background: showEDI ? '#7C3AED' : C.bgSecondary,
                border:`1px solid ${showEDI ? '#7C3AED' : C.border}`,
                color: showEDI ? '#fff' : C.textMid,
                fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
                transition:'all 0.2s',
              }}>💊</button>
          )}

          <button onClick={() => setShowSettings(true)} style={{
            width:'38px', height:'38px', borderRadius:'50%',
            background:C.bgSecondary, border:`1px solid ${C.border}`,
            color:C.textMid, fontSize:'16px',
            display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
          }}>⚙</button>
          <button onClick={() => setShowSideProject(s => !s)} title="Quick Task"
            style={{
              width:'38px', height:'38px', borderRadius:'50%',
              background: showSideProject ? C.blue : C.bgSecondary,
              border:`1px solid ${showSideProject ? C.blue : C.border}`,
              color: showSideProject ? '#fff' : C.textMid,
              fontSize:'16px', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
              transition:'all 0.2s',
            }}>⚡</button>
          <div style={{
            width:'8px', height:'8px', borderRadius:'50%', flexShrink:0,
            background: wsConnected ? C.success : C.error,
            boxShadow: wsConnected ? `0 0 0 3px rgba(26,127,55,0.15)` : 'none',
          }} title={wsConnected ? 'Connected' : 'Disconnected'} />
        </div>

        {/* Secure mode banner */}
        {secure && (
          <div style={{
            padding:'8px 16px', background:C.secureLight,
            borderBottom:'1px solid rgba(16,69,184,0.15)',
            fontSize:'12px', color:C.secure,
            display:'flex', alignItems:'center', gap:'8px', flexShrink:0,
          }}>
            <span>🛡</span>
            <span><strong>HIPAA Secure Mode</strong> — PHI de-identified before sending · AES-256 local</span>
          </div>
        )}

        {/* No key banner */}
        {(() => {
          const sel = models.find(m => m.id === selectedModel)
          if (sel && !sel.available && !sel.local) {
            return (
              <div style={{ padding:'8px 16px', background:'#FFFBEB', borderBottom:'1px solid #FFD84D', fontSize:'12px', color:'#92400E', display:'flex', alignItems:'center', gap:'8px', flexShrink:0 }}>
                <span>🔑</span>
                <span><strong>No API key for {PROVIDER_META[sel.provider]?.label}.</strong> Tap <button onClick={() => setShowSettings(true)} style={{ background:'none', border:'none', color:C.blue, fontWeight:600, fontSize:'12px', cursor:'pointer', padding:0, textDecoration:'underline' }}>Settings ⚙</button> → API Keys to add it.</span>
              </div>
            )
          }
          return null
        })()}

        {/* Messages */}
        <div style={{ flex:1, overflowY:'auto', padding: isMobile ? '16px 12px' : '24px 24px 16px', WebkitOverflowScrolling:'touch' }}>
          {messages.length === 0 && (
            <div style={{ height:'100%', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:'14px', paddingBottom:'60px' }}>
              <GoldEgg phase={eggPhase} size={80} />
              <div style={{ fontWeight:700, fontSize:'22px', color: rexxieMode ? C.rexxie : C.text, letterSpacing:'-0.3px', transition:'color 0.3s' }}>
                {rexxieMode ? `Hey, Kato 🐢` : greeting}
              </div>
              <div style={{ fontSize:'14px', color:C.textMid, maxWidth:'320px', textAlign:'center', lineHeight:1.6 }}>
                {rexxieMode
                  ? 'This is your private space. What\'s on your mind?'
                  : 'REX encrypts every conversation locally. Toggle HIPAA Secure to shield sensitive identifiers.'}
              </div>
              {!rexxieMode && (
                <div style={{ display:'flex', gap:'8px', flexWrap:'wrap', justifyContent:'center', marginTop:'4px' }}>
                  {['Local-first AI','AES-256 encrypted','Multi-provider','PHI shielding'].map(t => (
                    <span key={t} style={{ padding:'5px 12px', borderRadius:'20px', border:`1px solid ${C.border}`, fontSize:'12px', color:C.textMid, background:C.white }}>{t}</span>
                  ))}
                </div>
              )}
            </div>
          )}
          {messages.map(m => <MessageBubble key={m.id} msg={m} secure={secure} />)}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: isMobile ? '8px 12px' : '10px 18px',
          paddingBottom: isMobile ? 'calc(8px + env(safe-area-inset-bottom))' : '16px',
          background:C.white,
          borderTop:`1px solid ${secure ? 'rgba(16,69,184,0.15)' : C.border}`,
          boxShadow:'0 -2px 12px rgba(0,0,0,0.04)',
          flexShrink:0,
        }}>
          <div style={{
            display:'flex', alignItems:'flex-end', gap:'8px',
            background: rexxieMode ? C.rexxieBg : C.bg,
            border:`1.5px solid ${input ? (rexxieMode ? C.rexxie : secure ? C.secure : C.blue) : rexxieMode ? C.rexxieMid : C.border}`,
            borderRadius:'14px', padding:'8px 8px 8px 14px',
            boxShadow: input ? `0 0 0 3px rgba(${rexxieMode ? '155,79,114' : secure ? '16,69,184' : '0,102,255'},0.10)` : 'none',
            transition:'all 0.3s',
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => {
                setInput(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
              }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !isMobile) { e.preventDefault(); send() } }}
              placeholder={rexxieMode ? '🐢 Just us here, Kato…' : secure ? '🛡 HIPAA Secure — PHI will be shielded…' : 'Message REX…'}
              disabled={streaming || !wsConnected}
              rows={1}
              style={{
                flex:1, resize:'none', background:'transparent',
                fontSize:'16px', lineHeight:1.5,
                maxHeight:'120px', minHeight:'24px',
                color:C.text,
                WebkitAppearance:'none',
              }}
            />
            <button
              onClick={send}
              disabled={!input.trim() || streaming || !wsConnected}
              style={{
                width:'38px', height:'38px', borderRadius:'10px',
                background: (input.trim() && !streaming && wsConnected) ? (rexxieMode ? C.rexxie : secure ? C.secure : C.blue) : C.border,
                color: (input.trim() && !streaming && wsConnected) ? '#fff' : C.textMuted,
                fontSize:'18px', display:'flex', alignItems:'center', justifyContent:'center',
                flexShrink:0,
                boxShadow: (input.trim() && !streaming && wsConnected) ? `0 2px 8px rgba(${rexxieMode ? '155,79,114' : '0,102,255'},0.3)` : 'none',
                transition:'background 0.25s',
              }}
            >
              {streaming ? (
                <div style={{ width:'14px', height:'14px', border:'2px solid currentColor', borderTopColor:'transparent', borderRadius:'50%', animation:'spin 0.6s linear infinite' }} />
              ) : '↑'}
            </button>
          </div>
          <div style={{ marginTop:'5px', fontSize:'11px', color: rexxieMode ? C.rexxie : C.textMuted, textAlign:'center', transition:'color 0.3s' }}>
            {wsConnected ? (rexxieMode ? '🐢 Private · Triple-encrypted · Chairman only' : secure ? '🛡 Secure · PHI de-identified · AES-256' : '🔐 AES-256 encrypted') : '⚡ Connecting…'}
          </div>
        </div>
      </div>

      {showSettings && (
        <SettingsModal
          onClose={() => { setShowSettings(false); loadHealth(); loadModels() }}
          health={health}
          appearance={appearance}
          onAppearanceChange={a => { setAppearance(a); saveAppearance(a) }}
        />
      )}

      {/* Calendar Panel */}
      {showCalendar && <CalendarPanel onClose={() => setShowCalendar(false)} pendingPdfs={pendingPdfs} />}

      {/* Staff Compliance Panel — chairman/admin only */}
      {showStaff && isPrivileged(currentUser) && <StaffPanel onClose={() => setShowStaff(false)} authToken={getAuthToken()} />}

      {/* Manage Employee Access Panel — chairman only */}
      {showEmployeePerms && currentUser?.role === 'chairman' && <EmployeePermissionsPanel onClose={() => setShowEmployeePerms(false)} authToken={getAuthToken()} />}

      {/* Client Attendance Panel */}
      {showAttendance && <AttendancePanel onClose={() => setShowAttendance(false)} />}
      {showGOJ && <GOJStatsPanel onClose={() => setShowGOJ(false)} authToken={getAuthToken()} />}
      {showDocumentVault && <DocumentVaultPanel onClose={() => setShowDocumentVault(false)} authToken={getAuthToken()} />}

      {/* Chairman Audit Trail */}
      {showAudit && <ChairmanAuditPanel onClose={() => setShowAudit(false)} />}

      {/* EDI 837 / 835 Panel */}
      {showEDI && <EDIPanel onClose={() => setShowEDI(false)} />}

      {/* Gmail Panel */}
      {showGmail && <GmailPanel onClose={() => setShowGmail(false)} />}

      {/* Upload / Documents Panel */}
      {showUpload && <UploadPanel onClose={() => setShowUpload(false)} />}

      {/* Telegram / GOJ Feed Panel */}
      {showTelegram && <TelegramFeedPanel onClose={() => setShowTelegram(false)} />}

      {/* Side Project floating panel */}
      {showSideProject && <SideProject onClose={() => setShowSideProject(false)} />}

      {/* Floating Quick Task button — always visible bottom-right */}
      {!showSideProject && (
        <button
          onClick={() => setShowSideProject(true)}
          title="Quick Task"
          style={{
            position:'fixed', bottom:'20px', right:'20px', zIndex:700,
            width:'48px', height:'48px', borderRadius:'50%',
            background:`linear-gradient(135deg,${C.blue},${C.blueDark})`,
            color:'#fff', fontSize:'20px',
            display:'flex', alignItems:'center', justifyContent:'center',
            boxShadow:'0 4px 20px rgba(0,102,255,0.35)',
            transition:'transform 0.2s, box-shadow 0.2s',
          }}>⚡</button>
      )}
    </div>
    </ThemeCtx.Provider>
  )
}
