import * as Collapsible from '@radix-ui/react-collapsible'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowRight } from '@phosphor-icons/react/dist/csr/ArrowRight'
import { ArrowUpRight } from '@phosphor-icons/react/dist/csr/ArrowUpRight'
import { Check } from '@phosphor-icons/react/dist/csr/Check'
import { CloudArrowUp } from '@phosphor-icons/react/dist/csr/CloudArrowUp'
import { Headphones } from '@phosphor-icons/react/dist/csr/Headphones'
import { House } from '@phosphor-icons/react/dist/csr/House'
import { Info } from '@phosphor-icons/react/dist/csr/Info'
import { LockKey } from '@phosphor-icons/react/dist/csr/LockKey'
import { Play } from '@phosphor-icons/react/dist/csr/Play'
import { Plus } from '@phosphor-icons/react/dist/csr/Plus'
import { Record } from '@phosphor-icons/react/dist/csr/Record'
import { SignIn } from '@phosphor-icons/react/dist/csr/SignIn'
import { Sparkle } from '@phosphor-icons/react/dist/csr/Sparkle'
import { Trash } from '@phosphor-icons/react/dist/csr/Trash'
import { VideoCamera } from '@phosphor-icons/react/dist/csr/VideoCamera'
import { WarningCircle } from '@phosphor-icons/react/dist/csr/WarningCircle'
import { X } from '@phosphor-icons/react/dist/csr/X'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from './api'
import type { AssessmentResult, Bootstrap, CriterionView, DemoSummary, JobState, MediaItem } from './types'

function useBootstrap() {
  const [data, setData] = useState<Bootstrap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(() => {
    api.bootstrap().then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : 'The app could not start.'))
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  return { data, error, refresh }
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" to="/" aria-label="DUET SPEAK home">
      <span className="brand-mark"><span>DUET</span><i>/</i><span>SPEAK</span></span>
      {!compact && <small>NCKH12 Speaking Coach</small>}
    </Link>
  )
}

function Shell({ children, tone = 'light', bootstrap, refresh }: { children: React.ReactNode; tone?: 'light' | 'dark'; bootstrap: Bootstrap | null; refresh: () => void }) {
  const [params] = useSearchParams()
  const presenter = params.get('presenter') === '1'
  const [presenterOpen, setPresenterOpen] = useState(false)
  return (
    <div className={`app-shell tone-${tone}`}>
      <header className="topbar">
        <Brand />
        <nav aria-label="Primary navigation">
          <NavLink to="/"><House weight="bold" /> <span>Home</span></NavLink>
          <NavLink to="/assess"><Record weight="fill" /> <span>Assess</span></NavLink>
          <NavLink to="/recent"><VideoCamera weight="bold" /> <span>Recent</span></NavLink>
        </nav>
        <div className="top-actions">
          <span className="privacy-label"><LockKey weight="bold" /> Local and private</span>
          {presenter && <button className="icon-button" onClick={() => setPresenterOpen(true)} aria-label="Presenter controls"><Sparkle weight="fill" /></button>}
        </div>
      </header>
      <main id="main-content">{children}</main>
      <footer>
        <Brand compact />
        <p>Evidence-based controlled-reading practice. No CEFR, B2 or IELTS score.</p>
        <Link to="/legacy">Legacy interface</Link>
      </footer>
      <PresenterDialog open={presenterOpen} onOpenChange={setPresenterOpen} state={bootstrap?.chatgpt ?? null} onChanged={refresh} />
    </div>
  )
}

function PresenterDialog({ open, onOpenChange, state, onChanged }: { open: boolean; onOpenChange: (value: boolean) => void; state: Bootstrap['chatgpt'] | null; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const connect = async () => {
    setBusy(true); setMessage('A secure ChatGPT sign-in window is opening.')
    try {
      const response = await api.connectChatGPT()
      setMessage(response.state === 'PENDING' ? 'Complete sign-in in the secure browser window, then reopen this panel.' : 'Connection status updated.')
      window.setTimeout(onChanged, 2500)
    }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Connection could not be completed.') }
    finally { setBusy(false) }
  }
  const disconnect = async () => {
    setBusy(true)
    try { await api.disconnectChatGPT(); setMessage('Disconnected on this computer.'); onChanged() }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Disconnect could not be completed.') }
    finally { setBusy(false) }
  }
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Close className="dialog-close" aria-label="Close"><X /></Dialog.Close>
          <p className="kicker">Presenter tools</p>
          <Dialog.Title>Personalized feedback connection</Dialog.Title>
          <Dialog.Description>Scores stay local and frozen. Only allowlisted text evidence can be used for optional wording.</Dialog.Description>
          <div className={`connection-state ${state?.connected ? 'connected' : ''}`}>
            <span>{state?.connected ? <Check weight="bold" /> : <SignIn weight="bold" />}</span>
            <div>
              <strong>{state?.connected ? 'ChatGPT connected' : 'ChatGPT not connected'}</strong>
              <p>{state?.connected ? `${state.account_label ?? 'Connected account'} · ${state.selected_model ?? 'Choose a model'}` : 'Deterministic evidence-based feedback remains available.'}</p>
            </div>
          </div>
          {state?.connected && state.models && state.models.length > 0 && (
            <label className="model-select">Feedback model
              <select value={state.selected_model ?? ''} onChange={(event) => api.selectModel(event.target.value).then(onChanged)}>
                {state.models.map((model) => <option key={model.slug} value={model.slug}>{model.display_name}</option>)}
              </select>
            </label>
          )}
          {message && <p className="inline-message">{message}</p>}
          <div className="dialog-actions">
            {state?.connected
              ? <button className="button secondary" onClick={disconnect} disabled={busy}>Disconnect</button>
              : <button className="button primary" onClick={connect} disabled={busy}>Continue with ChatGPT <ArrowUpRight /></button>}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function App() {
  const { data, error, refresh } = useBootstrap()
  return (
    <Routes>
      <Route path="/" element={<Shell bootstrap={data} refresh={refresh}><Home bootstrap={data} error={error} /></Shell>} />
      <Route path="/assess" element={<Shell tone="dark" bootstrap={data} refresh={refresh}><Assessment demos={data?.demos ?? []} /></Shell>} />
      <Route path="/recent" element={<Shell bootstrap={data} refresh={refresh}><Recent /></Shell>} />
      <Route path="/results/:source/:id" element={<Shell bootstrap={data} refresh={refresh}><Results /></Shell>} />
      <Route path="/legacy" element={<Legacy />} />
      <Route path="*" element={<Shell bootstrap={data} refresh={refresh}><NotFound /></Shell>} />
    </Routes>
  )
}

function Home({ bootstrap, error }: { bootstrap: Bootstrap | null; error: string | null }) {
  const navigate = useNavigate()
  const reduceMotion = useReducedMotion()
  return (
    <>
      <section className="hero">
        <motion.div className="hero-copy" initial={reduceMotion ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .55 }}>
          <p className="kicker">Speaking intelligence studio</p>
          <h1>Every Duet is a<br /><em>chance to grow.</em></h1>
          <p className="hero-sub">Turn speaking practice into evidence you can understand.</p>
          <div className="hero-actions">
            <button className="button primary" onClick={() => navigate('/assess?path=demo')}>Try a Demo <Play weight="fill" /></button>
            <button className="button secondary" onClick={() => navigate('/assess?path=upload')}>Assess a Duet <ArrowRight /></button>
          </div>
        </motion.div>
        <motion.div className="hero-art" initial={reduceMotion ? false : { opacity: 0, scale: .97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: .7, delay: .08 }}>
          <img src="/assets/duet-speak-audio-sculpture.webp" alt="" aria-hidden="true" />
          <div className="hero-signal" aria-hidden="true">
            {Array.from({ length: 28 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17) % 58)}%` }} />)}
          </div>
          <div className="hero-caption">
            <span><Headphones weight="fill" /> Your voice, isolated locally</span>
            <strong>Evidence before advice</strong>
          </div>
        </motion.div>
      </section>
      <section className="home-proof" aria-label="Product principles">
        <p>Completed Duet in.</p><span /> <p>Learner voice found.</p><span /> <p>Four grounded views out.</p>
      </section>
      <section className="demo-section">
        <div className="section-heading">
          <p className="kicker">Fast Demo</p>
          <h2>Hear the evidence tell a different story.</h2>
          <p>Three genuine development examples. Scores are frozen machine outputs, never placeholders.</p>
        </div>
        {error && <ErrorNotice message={error} />}
        <div className="demo-strip">
          {(bootstrap?.demos ?? []).map((demo, index) => <DemoCard key={demo.id} demo={demo} index={index} />)}
          {!bootstrap && !error && Array.from({ length: 3 }, (_, index) => <div className="demo-card skeleton" key={index} />)}
        </div>
      </section>
      <section className="privacy-story">
        <div className="privacy-number">01</div>
        <div><h2>Your recording stays on this computer.</h2><p>Assessment, thumbnails and recent results remain in a private local workspace. Optional remote feedback uses allowlisted text only.</p></div>
        <Link className="text-link" to="/recent">Open Recent Videos <ArrowRight /></Link>
      </section>
    </>
  )
}

function DemoCard({ demo, index }: { demo: DemoSummary; index: number }) {
  const navigate = useNavigate()
  return (
    <motion.button className={`demo-card demo-${index + 1}`} whileHover={{ y: -6 }} transition={{ duration: .22 }} onClick={() => navigate(`/results/demo/${demo.id}`)}>
      <div className="demo-thumb"><img src={demo.thumbnail_url} alt="" /><span><Play weight="fill" /></span></div>
      <div className="demo-meta"><small>{demo.role}</small><strong>{demo.display_name}</strong><span>Open genuine result <ArrowUpRight /></span></div>
    </motion.button>
  )
}

function Assessment({ demos }: { demos: DemoSummary[] }) {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'upload' | 'tiktok'>(params.get('path') === 'tiktok' ? 'tiktok' : 'upload')
  const [recent, setRecent] = useState<MediaItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tiktokUrl, setTikTokUrl] = useState('')
  const [preview, setPreview] = useState<{ title: string; author_name: string; thumbnail_url?: string } | null>(null)
  const [permission, setPermission] = useState(false)
  const [job, setJob] = useState<JobState | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const requestedMediaStarted = useRef<string | null>(null)
  const refresh = useCallback(() => api.recent().then(setRecent).catch(() => setRecent([])), [])
  useEffect(() => { void refresh() }, [refresh])

  useEffect(() => {
    if (!job || !['QUEUED', 'RUNNING'].includes(job.state)) return
    const timer = window.setInterval(async () => {
      try {
        const next = await api.job(job.job_id)
        setJob(next)
        if (next.state === 'COMPLETE') { window.clearInterval(timer); navigate(`/results/media/${next.media_id}`) }
        if (next.state === 'FAILED') window.clearInterval(timer)
      } catch { window.clearInterval(timer); setError('Assessment status could not be refreshed.') }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [job, navigate])

  const assess = async (mediaId: string) => {
    setError(null)
    try { setJob(await api.startAssessment(mediaId)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Assessment could not start.') }
  }
  useEffect(() => {
    const requested = params.get('media')
    if (requested && requestedMediaStarted.current !== requested && !job) {
      requestedMediaStarted.current = requested
      void assess(requested)
    }
  }, [params, job])
  const handleFile = async (file?: File) => {
    if (!file) return
    setUploading(true); setError(null)
    try { const response = await api.upload(file); await refresh(); await assess(response.item.media_id) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'This file could not be added.') }
    finally { setUploading(false) }
  }
  const doPreview = async () => {
    setError(null); setPreview(null)
    try { setPreview(await api.previewTikTok(tiktokUrl)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Preview is unavailable.') }
  }
  const doImport = async () => {
    setError(null); setUploading(true)
    try { const response = await api.importTikTok(tiktokUrl, permission); await refresh(); await assess(response.item.media_id) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Import could not be completed.') }
    finally { setUploading(false) }
  }
  return (
    <div className="assessment-page">
      <section className="workspace-intro">
        <p className="kicker">Assessment studio</p>
        <h1>Bring in a completed Duet.<br /><em>We will listen for the learner.</em></h1>
        <p>Local scoring uses the frozen NCKH12 pipeline. No media is uploaded to a scoring service.</p>
      </section>
      <section className="workspace-grid">
        <div className="import-panel">
          <div className="segmented" role="tablist" aria-label="Add a video">
            <button className={tab === 'upload' ? 'active' : ''} onClick={() => setTab('upload')} role="tab" aria-selected={tab === 'upload'}><CloudArrowUp /> Upload video</button>
            <button className={tab === 'tiktok' ? 'active' : ''} onClick={() => setTab('tiktok')} role="tab" aria-selected={tab === 'tiktok'}><VideoCamera /> TikTok link</button>
          </div>
          <AnimatePresence mode="wait">
            {tab === 'upload' ? (
              <motion.div key="upload" className={`upload-zone ${dragging ? 'dragging' : ''}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false) }}
                onDrop={(event) => { event.preventDefault(); setDragging(false); void handleFile(event.dataTransfer.files[0]) }}>
                <input ref={fileInput} type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm" onChange={(event) => void handleFile(event.target.files?.[0])} />
                <div className="upload-icon"><Plus weight="bold" /></div>
                <h2>{uploading ? 'Preparing your video...' : 'Drop a completed Duet here'}</h2>
                <p>MP4, MOV, MKV or WebM. Up to 500 MB and five minutes.</p>
                <button className="button light" onClick={() => fileInput.current?.click()} disabled={uploading}>Choose a video</button>
              </motion.div>
            ) : (
              <motion.div key="tiktok" className="tiktok-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <h2>Preview a public TikTok</h2><p>Nothing is imported until you preview the link and confirm permission.</p>
                <label>TikTok video URL<input value={tiktokUrl} onChange={(event) => setTikTokUrl(event.target.value)} placeholder="https://www.tiktok.com/@creator/video/..." /></label>
                <button className="button light" onClick={doPreview} disabled={!tiktokUrl}>Preview link</button>
                {preview && <div className="tiktok-preview">{preview.thumbnail_url && <img src={preview.thumbnail_url} alt="TikTok preview" />}<div><strong>{preview.title}</strong><span>{preview.author_name}</span><label className="consent"><input type="checkbox" checked={permission} onChange={(event) => setPermission(event.target.checked)} /> I own this video or have permission to use it.</label><button className="button primary" onClick={doImport} disabled={!permission || uploading}>Import and assess <ArrowRight /></button></div></div>}
              </motion.div>
            )}
          </AnimatePresence>
          {error && <ErrorNotice message={error} dark />}
          {job && <AnalysisState job={job} />}
        </div>
        <aside className="demo-rail">
          <span className="rail-label">Or start in seconds</span>
          <h2>Try a frozen demo</h2>
          {demos.map((demo, index) => <button key={demo.id} onClick={() => navigate(`/results/demo/${demo.id}`)}><span>0{index + 1}</span><div><strong>{demo.short_id}</strong><small>{demo.role}</small></div><ArrowRight /></button>)}
          <p><Check weight="bold" /> Genuine machine outputs</p><p><Check weight="bold" /> Works offline</p>
        </aside>
      </section>
      {recent.length > 0 && <section className="workspace-recent"><div><h2>Continue where you left off</h2><Link to="/recent">View all <ArrowRight /></Link></div><div className="mini-recent">{recent.slice(0, 3).map((item) => <MediaRow key={item.media_id} item={item} onAssess={assess} />)}</div></section>}
    </div>
  )
}

function AnalysisState({ job }: { job: JobState }) {
  const active = job.state === 'RUNNING' || job.state === 'QUEUED'
  return <motion.div key={`${job.state}-${job.message}`} className={`analysis-state ${job.state.toLowerCase()}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><span className={active ? 'activity-ring' : ''}>{job.state === 'FAILED' ? <WarningCircle /> : <Sparkle weight="fill" />}</span><div><strong>{job.state === 'COMPLETE' ? 'Assessment ready' : job.state === 'FAILED' ? 'Assessment paused' : 'Listening to the recording'}</strong><p>{job.error ?? job.message}</p></div></motion.div>
}

function Results() {
  const { source = '', id = '' } = useParams()
  const navigate = useNavigate()
  const routeKey = `${source}:${id}`
  const [loaded, setLoaded] = useState<{ key: string; result: AssessmentResult | null; error: string | null }>({ key: '', result: null, error: null })
  useEffect(() => {
    let active = true
    const promise = source === 'demo' ? api.demoResult(id) : source === 'media' ? api.mediaResult(id) : Promise.reject(new Error('Unknown result source.'))
    promise
      .then((result) => { if (active) setLoaded({ key: routeKey, result, error: null }) })
      .catch((reason) => { if (active) setLoaded({ key: routeKey, result: null, error: reason instanceof Error ? reason.message : 'Result is unavailable.' }) })
    return () => { active = false }
  }, [source, id, routeKey])
  const result = loaded.key === routeKey ? loaded.result : null
  const error = loaded.key === routeKey ? loaded.error : null
  if (error) return <div className="state-page"><ErrorNotice message={error} /><button className="button primary" onClick={() => navigate('/assess')}>Return to assessment</button></div>
  if (!result) return <div className="state-page"><span className="activity-ring dark" /><h1>Opening your speaking snapshot</h1></div>
  if (result.status === 'NOT_SCORABLE') return <div className="state-page"><WarningCircle size={42} /><h1>This recording could not be scored reliably.</h1><p>Try a completed Duet with a clearer learner voice and less background interference.</p><button className="button primary" onClick={() => navigate('/assess')}>Try another video</button></div>
  return <ResultStory result={result} />
}

function ResultStory({ result }: { result: AssessmentResult }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const criteria = result.criteria.items
  const feedback = result.feedback
  return (
    <article className="result-story">
      <section className="result-hero">
        <div className="result-title"><p className="kicker">Your speaking snapshot</p><h1>{result.display_name}</h1><p>Topic: {result.target_topic}</p><div className="result-badges"><span>Development / preliminary</span><span>{result.feedback.source === 'CHATGPT' ? 'Personalized wording' : 'Evidence-based feedback'}</span></div><OverallPractice overall={result.overall_practice_score} /></div>
        <div className="media-stage">
          <video controls preload="metadata" src={result.media.video_url} aria-label="Completed Duet video" />
          {result.media.audio_url && <div className="audio-player"><Headphones weight="fill" /><div><strong>Learner audio</strong><small>Raw cropped from the completed Duet</small></div><audio controls preload="metadata" src={result.media.audio_url} /></div>}
        </div>
      </section>

      <section className="criteria-story" aria-labelledby="criteria-title">
        <div className="criteria-heading"><p className="kicker">Four views, one recording</p><h2 id="criteria-title">What the evidence noticed.</h2><p>The summary above is descriptive. Each criterion below keeps its own scientific status.</p></div>
        <CriterionFeature criterion={criteria.fluency} evidence={result.evidence.fluency} />
        <div className="criterion-reading">
          <div className={`criterion-number ${criteria.completeness.available ? '' : 'unavailable'}`}>{criteria.completeness.available ? <><span>{criteria.completeness.display_value}</span><sup>%</sup></> : <span>Unavailable</span>}</div>
          <div><h3>{criteria.completeness.label}</h3><p>{criteria.completeness.available ? `${result.completeness.matched_word_count} target words matched in sequence. Differences may include ASR uncertainty and are not confirmed learner errors.` : 'This measure could not be produced for this recording.'}</p><span className="status-tag measured">{criteria.completeness.badge}</span></div>
        </div>
        <div className="criterion-pair">
          <CriterionEditorial criterion={criteria.pronunciation} prompts={result.evidence.word_review_prompts} />
          <CriterionEditorial criterion={criteria.prosody} />
        </div>
      </section>

      <section className="feedback-section">
        <div className="feedback-lead"><p className="kicker">Your next take</p><h2>Keep what works.<br /><em>Refine one thing.</em></h2><p>{feedback.source === 'CHATGPT' ? 'Personalized wording grounded in the same frozen evidence.' : 'Deterministic wording grounded in measured evidence.'}</p></div>
        <div className="feedback-notes">
          <FeedbackNote index="01" label="Keep" text={feedback.strength.text} tone="mint" />
          <FeedbackNote index="02" label="Focus" text={feedback.focus_next.text} tone="apricot" />
          <FeedbackNote index="03" label="Try" text={feedback.try_this.text} tone="periwinkle" />
        </div>
      </section>

      <Collapsible.Root open={evidenceOpen} onOpenChange={setEvidenceOpen} className="evidence-section">
        <Collapsible.Trigger className="evidence-trigger"><div><p className="kicker">Trace the result</p><h2>Explore the evidence</h2></div><span>{evidenceOpen ? 'Close' : 'Open'} <Plus className={evidenceOpen ? 'rotated' : ''} /></span></Collapsible.Trigger>
        <Collapsible.Content className="evidence-content">
          <div className="passage-block"><span>Scored passage</span><p>{result.target_text}</p></div>
          <div className="passage-block transcript"><span>Learner transcript</span><p>{result.transcript}</p></div>
          {result.evidence.word_review_prompts?.length > 0 && <div className="review-words"><span>Words to review, not confirmed errors</span><div>{result.evidence.word_review_prompts.map((row) => <b key={row.word}>{row.word}</b>)}</div></div>}
          <div className="fluency-facts">
            <EvidenceFact label="Speech rate" value={formatEvidence(result.evidence.fluency.speech_rate_wpm, ' wpm')} />
            <EvidenceFact label="Long pauses" value={formatEvidence(result.evidence.fluency.long_pause_count)} />
            <EvidenceFact label="Longest pause" value={formatEvidence(result.evidence.fluency.longest_pause_sec, ' s')} />
            <EvidenceFact label="Mean run" value={formatEvidence(result.evidence.fluency.mean_length_of_run_words, ' words')} />
          </div>
          <p className="evidence-warning"><WarningCircle /> {result.completeness.warning}</p>
        </Collapsible.Content>
      </Collapsible.Root>
      <section className="result-next"><div><h2>Ready for another take?</h2><p>Keep this result in Recent Videos or assess a new completed Duet.</p></div><div><button className="button primary" onClick={() => navigate('/assess')}>Assess another Duet <ArrowRight /></button><button className="button secondary" onClick={() => navigate('/recent')}>View Recent Videos</button></div></section>
      {params.get('presenter') === '1' && <section className="presenter-provenance"><p className="kicker">Presenter provenance</p><div><span>Assessment source<strong>{result.provenance.audio_source_type}</strong></span><span>Inference<strong>{result.provenance.genuine_frozen_inference ? 'Frozen configuration' : 'Unavailable'}</strong></span><span>Product summary<strong>{result.overall_practice_score?.presenter_designation ?? 'UNAVAILABLE'}</strong></span><span>Research membership<strong>FALSE</strong></span></div></section>}
    </article>
  )
}

function OverallPractice({ overall }: { overall: AssessmentResult['overall_practice_score'] }) {
  const [params] = useSearchParams()
  const reduced = useReducedMotion()
  if (!overall) return <div className="overall-unavailable"><strong>Overall Practice Score unavailable</strong><span>Overall Practice Score requires all four assessment measures.</span></div>
  return (
    <motion.div className="overall-practice" initial={reduced ? false : { opacity: 0, filter: 'blur(8px)', scale: .98 }} animate={{ opacity: 1, filter: 'blur(0px)', scale: 1 }} transition={{ duration: .45, delay: .18 }}>
      <div className="overall-value"><span>{overall.display_value.toFixed(1)}</span><sup>/ 5</sup></div>
      <div className="overall-copy"><div><h2>{overall.label}</h2><span>Descriptive</span></div><p>A summary of Pronunciation, Fluency, Prosody and Reading Completeness.</p><details className="overall-info"><summary aria-label="About the Overall Practice Score"><Info weight="bold" /> About this summary</summary><p>{overall.student_note}</p>{params.get('presenter') === '1' && <code>{overall.presenter_designation}</code>}</details></div>
    </motion.div>
  )
}

function CriterionFeature({ criterion, evidence }: { criterion: CriterionView; evidence: Record<string, number | null> }) {
  return <motion.div className="criterion-feature" initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: .2 }} transition={{ duration: .45 }}><div className="feature-top"><span className="status-tag measured">{criterion.badge}</span></div><div className={`feature-score ${criterion.available ? '' : 'unavailable'}`}><span>{criterion.available ? criterion.display_value?.toFixed(1) : 'Unavailable'}</span>{criterion.available && <sup>/ 5</sup>}</div><h3>{criterion.label}</h3><p>{criterion.available ? criterion.description : 'This measure could not be produced for this recording.'}</p><div className="signal-line" aria-hidden="true">{Array.from({ length: 38 }, (_, index) => <i key={index} style={{ height: `${12 + ((index * 29) % 76)}%` }} />)}</div><div className="feature-facts"><span>{formatEvidence(evidence.speech_rate_wpm, ' wpm')} <small>speech rate</small></span><span>{formatEvidence(evidence.long_pause_count)} <small>long pauses</small></span></div></motion.div>
}

function CriterionEditorial({ criterion, prompts = [] }: { criterion: CriterionView; prompts?: { word: string }[] }) {
  return <div className={`criterion-editorial ${criterion.key}`}><h3>{criterion.label}</h3><div className={`editorial-score ${criterion.available ? '' : 'unavailable'}`}>{criterion.available ? criterion.display_value?.toFixed(1) : 'Unavailable'}<small>{criterion.available ? '/ 5' : ''}</small></div><span className="status-tag preliminary" title={criterion.caveat ?? undefined}>{criterion.badge}</span><p>{criterion.available ? criterion.description : 'This measure could not be produced for this recording.'}</p>{prompts.length > 0 && criterion.available && <><strong className="mini-prompts-label">Words to review</strong><div className="mini-prompts">{prompts.slice(0, 3).map((row) => <span key={row.word}>{row.word}</span>)}</div></>}</div>
}

function FeedbackNote({ index, label, text, tone }: { index: string; label: string; text: string; tone: string }) {
  return <div className={`feedback-note ${tone}`}><span>{index}</span><div><strong>{label}</strong><p>{text}</p></div></div>
}

function EvidenceFact({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div> }
function formatEvidence(value: number | null | undefined, suffix = '') { return typeof value === 'number' ? `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}` : 'Unavailable' }

function Recent() {
  const navigate = useNavigate()
  const [items, setItems] = useState<MediaItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(() => api.recent().then(setItems).catch((reason) => setError(reason instanceof Error ? reason.message : 'Recent videos are unavailable.')), [])
  useEffect(() => { void refresh() }, [refresh])
  const remove = async (id: string) => {
    if (!window.confirm('Remove this video and its local result from Recent Videos?')) return
    try { await api.removeMedia(id); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'This item could not be removed.') }
  }
  return <div className="recent-page"><section className="library-heading"><p className="kicker">Private media library</p><h1>Recent Videos</h1><p>Your imported and uploaded Duets stay on this computer.</p><button className="button primary" onClick={() => navigate('/assess')}>Add a Duet <Plus weight="bold" /></button></section>{error && <ErrorNotice message={error} />}{items === null ? <div className="library-grid">{Array.from({ length: 3 }, (_, i) => <div className="library-card skeleton" key={i} />)}</div> : items.length === 0 ? <div className="empty-library"><div className="empty-orbit"><VideoCamera weight="duotone" /></div><h2>Your private library is ready.</h2><p>Upload a completed Duet or import a public TikTok with permission.</p><button className="button primary" onClick={() => navigate('/assess')}>Assess your first video <ArrowRight /></button></div> : <div className="library-grid">{items.map((item) => <LibraryCard key={item.media_id} item={item} onRemove={() => void remove(item.media_id)} />)}</div>}</div>
}

function LibraryCard({ item, onRemove }: { item: MediaItem; onRemove: () => void }) {
  const navigate = useNavigate()
  return <article className="library-card"><div className="library-thumb">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" /> : <VideoCamera weight="duotone" />}<span>{item.assessment_state === 'ASSESSED' ? 'Assessed' : 'Ready'}</span></div><div className="library-info"><small>{item.source_type === 'TIKTOK_LINK' ? 'TikTok import' : 'Local upload'} · {new Date(item.import_timestamp).toLocaleDateString()}</small><h2>{item.friendly_title}</h2><p>{Math.round(item.duration_seconds)} sec · {item.resolution.width} × {item.resolution.height}</p><div>{item.has_result ? <button className="button compact primary" onClick={() => navigate(`/results/media/${item.media_id}`)}>View result</button> : <button className="button compact primary" onClick={() => navigate(`/assess?media=${item.media_id}`)}>Assess</button>}<button className="icon-button danger" onClick={onRemove} aria-label={`Remove ${item.friendly_title}`}><Trash /></button></div></div></article>
}

function MediaRow({ item, onAssess }: { item: MediaItem; onAssess: (id: string) => void }) { return <div className="media-row">{item.thumbnail_url ? <img src={item.thumbnail_url} alt="" /> : <VideoCamera />}<div><strong>{item.friendly_title}</strong><span>{item.assessment_state === 'ASSESSED' ? 'Result available' : 'Ready to assess'}</span></div><button onClick={() => onAssess(item.media_id)}>Open <ArrowRight /></button></div> }

function ErrorNotice({ message, dark = false }: { message: string; dark?: boolean }) { return <div className={`error-notice ${dark ? 'dark' : ''}`} role="alert"><WarningCircle weight="fill" /><p>{message}</p></div> }
function NotFound() { return <div className="state-page"><h1>This page is not in the studio.</h1><Link className="button primary" to="/">Return home</Link></div> }
function Legacy() { useEffect(() => { window.location.href = 'http://127.0.0.1:8501/?mode=competition_demo' }, []); return <div className="state-page"><h1>Opening the legacy competition interface...</h1></div> }

export default App
