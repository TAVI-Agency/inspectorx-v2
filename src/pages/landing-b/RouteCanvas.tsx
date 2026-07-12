import { useEffect, useRef } from 'react'

/**
 * Сигнатура героя: десятки тусклых «маршрутов» сходятся в одной точке
 * пропуска и дальше идут одной яркой линией. Тезис продукта в одном кадре:
 * хаос требований → один понятный маршрут.
 *
 * Canvas 2D без зависимостей; уважает prefers-reduced-motion (один
 * статичный кадр) и останавливается вне вьюпорта.
 */

interface Route {
  y0: number // стартовая высота, доля от h
  amp: number
  phase: number
  speed: number
  alpha: number
  width: number
}

export function RouteCanvas({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let running = false
    let w = 0
    let h = 0
    let routes: Route[] = []

    const gate = () => ({ x: w * 0.84, y: h * 0.5 })

    function tracePath(y0frac: number, amp: number, phase: number, speed: number, time: number) {
      const g = gate()
      const y0 = y0frac * h
      const wob = Math.sin(time * speed + phase) * amp
      ctx!.beginPath()
      ctx!.moveTo(-60, y0 + wob * 0.4)
      ctx!.bezierCurveTo(
        w * 0.32, y0 + wob,
        w * 0.6, y0 + (g.y - y0) * 0.55 + wob * 0.5,
        g.x, g.y,
      )
      ctx!.lineTo(w + 60, g.y)
    }

    function draw(time: number) {
      ctx!.clearRect(0, 0, w, h)

      for (const r of routes) {
        tracePath(r.y0, r.amp, r.phase, r.speed, time)
        ctx!.strokeStyle = `rgba(46, 150, 138, ${r.alpha})`
        ctx!.lineWidth = r.width
        ctx!.stroke()
      }

      // яркий маршрут: широкое свечение + тонкая линия с градиентом
      const heroY = 0.42
      tracePath(heroY, 24, 0.4, 0.22, time)
      ctx!.strokeStyle = 'rgba(46, 196, 174, 0.18)'
      ctx!.lineWidth = 7
      ctx!.stroke()

      tracePath(heroY, 24, 0.4, 0.22, time)
      const grad = ctx!.createLinearGradient(0, 0, w, 0)
      grad.addColorStop(0, 'rgba(20, 140, 125, 0.3)')
      grad.addColorStop(0.65, '#2ec4ae')
      grad.addColorStop(1, '#eafaf6')
      ctx!.strokeStyle = grad
      ctx!.lineWidth = 2
      ctx!.stroke()

      // «пульс» — бегущие штрихи по яркому маршруту
      tracePath(heroY, 24, 0.4, 0.22, time)
      ctx!.save()
      ctx!.setLineDash([3, 34])
      ctx!.lineDashOffset = -time * 70
      ctx!.strokeStyle = 'rgba(255, 255, 255, 0.9)'
      ctx!.lineWidth = 3
      ctx!.stroke()
      ctx!.restore()

      // пункт пропуска: кольцо + расходящийся импульс
      const g = gate()
      ctx!.beginPath()
      ctx!.arc(g.x, g.y, 5.5 + Math.sin(time * 2) * 1.2, 0, Math.PI * 2)
      ctx!.strokeStyle = '#9fe8d9'
      ctx!.lineWidth = 1.6
      ctx!.stroke()
      ctx!.beginPath()
      ctx!.arc(g.x, g.y, 2.2, 0, Math.PI * 2)
      ctx!.fillStyle = '#ffffff'
      ctx!.fill()
      const pt = (time % 2.8) / 2.8
      ctx!.beginPath()
      ctx!.arc(g.x, g.y, 8 + pt * 36, 0, Math.PI * 2)
      ctx!.strokeStyle = `rgba(159, 232, 217, ${(1 - pt) * 0.45})`
      ctx!.lineWidth = 1
      ctx!.stroke()
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = canvas!.clientWidth
      h = canvas!.clientHeight
      canvas!.width = Math.max(1, Math.round(w * dpr))
      canvas!.height = Math.max(1, Math.round(h * dpr))
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      const n = w < 640 ? 14 : 26
      routes = Array.from({ length: n }, (_, i) => ({
        y0: (i + 0.5) / n + Math.sin(i * 3.1) * 0.03,
        amp: 18 + Math.abs(Math.sin(i * 7.3)) * 22 + (i % 5) * 5,
        phase: i * 1.7,
        speed: 0.22 + ((i * 37) % 10) / 22,
        alpha: 0.045 + ((i * 13) % 7) / 68,
        width: i % 6 === 0 ? 1.4 : 1,
      }))
      draw(reduced ? 0.7 : performance.now() / 1000)
    }

    function loop(ms: number) {
      if (!running) return
      draw(ms / 1000)
      raf = requestAnimationFrame(loop)
    }

    function start() {
      if (running || reduced) return
      running = true
      raf = requestAnimationFrame(loop)
    }
    function stop() {
      running = false
      cancelAnimationFrame(raf)
    }

    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) start()
      else stop()
    })
    io.observe(canvas)

    return () => {
      stop()
      ro.disconnect()
      io.disconnect()
    }
  }, [])

  return <canvas ref={ref} className={className} aria-hidden="true" />
}
