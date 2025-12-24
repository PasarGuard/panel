import * as React from 'react'

type SnowflakeType = 'dot' | 'svg'

type SnowflakeConfig = {
  type: SnowflakeType
  x: string
  size: string
  delay: string
  duration: string
  opacity: number
  sway: string
  swayDuration: string
}

const snowflakes: SnowflakeConfig[] = [
  { type: 'dot', x: '6%', size: '4px', delay: '-2s', duration: '12s', opacity: 0.55, sway: '10px', swayDuration: '6s' },
  { type: 'svg', x: '12%', size: '7px', delay: '-9s', duration: '15s', opacity: 0.7, sway: '14px', swayDuration: '8s' },
  { type: 'dot', x: '18%', size: '5px', delay: '-6s', duration: '13s', opacity: 0.6, sway: '12px', swayDuration: '7s' },
  { type: 'svg', x: '24%', size: '8px', delay: '-3s', duration: '16s', opacity: 0.7, sway: '16px', swayDuration: '9s' },
  { type: 'dot', x: '29%', size: '4px', delay: '-8s', duration: '11s', opacity: 0.5, sway: '9px', swayDuration: '6s' },
  { type: 'svg', x: '34%', size: '6px', delay: '-5s', duration: '14s', opacity: 0.65, sway: '13px', swayDuration: '8s' },
  { type: 'dot', x: '38%', size: '5px', delay: '-10s', duration: '13s', opacity: 0.55, sway: '11px', swayDuration: '7s' },
  { type: 'svg', x: '42%', size: '9px', delay: '-1s', duration: '15s', opacity: 0.7, sway: '18px', swayDuration: '10s' },
  { type: 'dot', x: '47%', size: '4px', delay: '-7s', duration: '12s', opacity: 0.5, sway: '10px', swayDuration: '6s' },
  { type: 'svg', x: '52%', size: '7px', delay: '-11s', duration: '14s', opacity: 0.65, sway: '15px', swayDuration: '9s' },
  { type: 'dot', x: '57%', size: '5px', delay: '-4s', duration: '13s', opacity: 0.6, sway: '12px', swayDuration: '7s' },
  { type: 'svg', x: '61%', size: '8px', delay: '-6s', duration: '16s', opacity: 0.7, sway: '17px', swayDuration: '10s' },
  { type: 'dot', x: '66%', size: '4px', delay: '-12s', duration: '11s', opacity: 0.5, sway: '9px', swayDuration: '6s' },
  { type: 'svg', x: '70%', size: '6px', delay: '-3s', duration: '14s', opacity: 0.65, sway: '13px', swayDuration: '8s' },
  { type: 'dot', x: '74%', size: '5px', delay: '-9s', duration: '12s', opacity: 0.55, sway: '11px', swayDuration: '7s' },
  { type: 'svg', x: '78%', size: '9px', delay: '-2s', duration: '15s', opacity: 0.7, sway: '18px', swayDuration: '10s' },
  { type: 'dot', x: '82%', size: '4px', delay: '-5s', duration: '12s', opacity: 0.5, sway: '10px', swayDuration: '6s' },
  { type: 'svg', x: '86%', size: '7px', delay: '-8s', duration: '14s', opacity: 0.65, sway: '15px', swayDuration: '9s' },
  { type: 'dot', x: '90%', size: '5px', delay: '-11s', duration: '13s', opacity: 0.6, sway: '12px', swayDuration: '7s' },
  { type: 'svg', x: '94%', size: '8px', delay: '-4s', duration: '16s', opacity: 0.7, sway: '17px', swayDuration: '10s' },
  { type: 'dot', x: '98%', size: '4px', delay: '-7s', duration: '12s', opacity: 0.5, sway: '10px', swayDuration: '6s' },
]

const snowflakePath =
  'M303.211 182.103c2.386 5.874-.441 12.57-6.315 14.957l-31.904 12.975 29.527 17.742c5.507 3.145 7.421 10.158 4.277 15.665-3.145 5.507-10.158 7.421-15.665 4.277a13.08 13.08 0 0 1-.439-.264l-29.525-17.74 3.523 34.273c.546 6.318-4.133 11.882-10.451 12.428-6.175.534-11.659-3.93-12.39-10.084l-5.282-51.399-56.423-33.895v65.822l41.335 31.001c5.073 3.805 6.101 11.002 2.296 16.075s-11.002 6.101-16.075 2.296l-27.557-20.667v34.446c0 6.341-5.141 11.482-11.482 11.482s-11.482-5.141-11.482-11.482v-34.446l-27.557 20.667c-5.073 3.805-12.27 2.777-16.075-2.296s-2.777-12.27 2.296-16.075l41.335-31.001v-65.822L92.76 214.941l-5.282 51.399c-.546 6.318-6.11 10.997-12.428 10.451s-10.997-6.11-10.451-12.428c.011-.122.023-.245.038-.367l3.523-34.273-29.525 17.74c-5.361 3.387-12.453 1.787-15.84-3.574s-1.787-12.453 3.574-15.84c.144-.091.291-.179.439-.264l29.527-17.742-31.904-12.975c-5.836-2.481-8.556-9.223-6.075-15.059 2.425-5.705 8.941-8.455 14.72-6.213l47.863 19.464 57.432-34.515-57.437-34.511-47.863 19.47c-5.912 2.294-12.564-.64-14.858-6.552-2.242-5.779.508-12.295 6.213-14.72l31.904-12.975-29.525-17.746c-5.507-3.145-7.421-10.158-4.277-15.664 3.145-5.507 10.158-7.421 15.664-4.277.148.085.294.173.439.264l29.525 17.74-3.523-34.273c-.647-6.308 3.942-11.947 10.25-12.594s11.947 3.942 12.594 10.25l5.282 51.399 56.422 33.9V74.632l-41.335-31.001c-5.075-3.803-6.106-10.999-2.303-16.074s10.999-6.106 16.074-2.303l.008.006 27.557 20.667V11.482C149.181 5.141 154.322 0 160.663 0s11.482 5.141 11.482 11.482v34.446l27.557-20.667c5.073-3.805 12.27-2.777 16.075 2.296s2.777 12.27-2.296 16.075l-41.335 31.001v65.823l56.421-33.904 5.282-51.399c.748-6.297 6.46-10.795 12.757-10.047 6.155.731 10.618 6.215 10.084 12.39l-3.523 34.273 29.525-17.74c5.361-3.387 12.453-1.787 15.84 3.575 3.387 5.361 1.786 12.453-3.575 15.84-.144.091-.29.179-.439.264L264.99 111.45l31.904 12.975c5.836 2.481 8.556 9.223 6.075 15.059-2.425 5.705-8.941 8.455-14.72 6.213l-47.863-19.464-57.432 34.515 57.437 34.511 47.863-19.464c5.864-2.392 12.557.423 14.948 6.287l.009.021z'

export default function Snowfall({ className = '' }: { className?: string }) {
  return (
    <div className={`snowfall ${className}`} aria-hidden="true">
      {snowflakes.map((flake, index) => (
        <span
          key={`${flake.type}-${index}`}
          className="snowfall__item"
          style={
            {
              '--snow-x': flake.x,
              '--snow-size': flake.size,
              '--snow-delay': flake.delay,
              '--snow-duration': flake.duration,
              '--snow-opacity': flake.opacity,
              '--snow-sway': flake.sway,
              '--snow-sway-duration': flake.swayDuration,
            } as React.CSSProperties
          }
        >
          <span className="snowfall__sway">
            {flake.type === 'dot' ? (
              <span className="snowfall__dot" />
            ) : (
              <svg className="snowfall__icon" viewBox="0 0 321.493 321.493" aria-hidden="true">
                <path d={snowflakePath} />
              </svg>
            )}
          </span>
        </span>
      ))}
    </div>
  )
}
