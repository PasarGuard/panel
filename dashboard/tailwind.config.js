/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        'input-placeholder': 'hsl(var(--input-placeholder))',
        ring: 'hsl(var(--ring))',
        chart: {
          1: 'hsl(var(--chart-1))',
          2: 'hsl(var(--chart-2))',
          3: 'hsl(var(--chart-3))',
          4: 'hsl(var(--chart-4))',
          5: 'hsl(var(--chart-5))',
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar-background))',
          foreground: 'hsl(var(--sidebar-foreground))',
          primary: 'hsl(var(--sidebar-primary))',
          'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
          accent: 'hsl(var(--sidebar-accent))',
          'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
          border: 'hsl(var(--sidebar-border))',
          ring: 'hsl(var(--sidebar-ring))',
        },
      },
      fontFamily: {
        body: ['Inter', 'Vazirmatn', 'ui-sans-serif', 'system-ui', 'sans-serif', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'],
      },
      keyframes: {
        pulseAnimation: {
          '0%': {
            boxShadow: '0 0 0 0px rgba(0, 0, 0, 0.4)',
          },
          '100%': {
            boxShadow: '0 0 0 10px rgba(0, 0, 0, 0)',
          },
        },
        greenPulseAnimation: {
          '0%': {
            boxShadow: '0 0 0 0px #66ff9975',
          },
          '100%': {
            boxShadow: '0 0 0 10px #66ff9900',
          },
        },
        redPulseAnimation: {
          '0%': {
            boxShadow: '0 0 0 0px #e53e3e8c',
          },
          '100%': {
            boxShadow: '0 0 0 10px #e53e3e00',
          },
        },
        orangePulseAnimation: {
          '0%': {
            boxShadow: '0 0 0 0px #fbd38d85',
          },
          '100%': {
            boxShadow: '0 0 0 10px #fbd38d00',
          },
        },
        'accordion-down': {
          from: {
            height: '0',
          },
          to: {
            height: 'var(--radix-accordion-content-height)',
          },
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)',
          },
          to: {
            height: '0',
          },
        },
        'fade-in': {
          '0%': {
            opacity: '0',
            transform: 'translateY(10px) scale(0.98)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateY(0) scale(1)',
          },
        },
        'fade-out': {
          '0%': {
            opacity: '1',
            transform: 'translateY(0) scale(1)',
          },
          '100%': {
            opacity: '0',
            transform: 'translateY(-10px) scale(0.98)',
          },
        },
        'slide-in': {
          '0%': {
            opacity: '0',
            transform: 'translateX(20px)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateX(0)',
          },
        },
        'slide-out': {
          '0%': {
            opacity: '1',
            transform: 'translateX(0)',
          },
          '100%': {
            opacity: '0',
            transform: 'translateX(-20px)',
          },
        },
        'telegram-shake': {
          '0%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-8px)' },
          '40%': { transform: 'translateX(8px)' },
          '60%': { transform: 'translateX(-4px)' },
          '80%': { transform: 'translateX(4px)' },
          '100%': { transform: 'translateX(0)' },
        },
        'bounce-in': {
          '0%': {
            transform: 'scale(0.8)',
            opacity: '0',
          },
          '50%': {
            transform: 'scale(1.05)',
            opacity: '0.7',
          },
          '100%': {
            transform: 'scale(1)',
            opacity: '1',
          },
        },
        'zoom-out': {
          '0%': {
            transform: 'scale(1.2)',
            opacity: '0',
          },
          '100%': {
            transform: 'scale(1)',
            opacity: '1',
          },
        },
        'zoom-in': {
          '0%': {
            transform: 'scale(1)',
            opacity: '1',
          },
          '100%': {
            transform: 'scale(1.2)',
            opacity: '0',
          },
        },
        'slide-up': {
          '0%': {
            transform: 'translateY(20px)',
            opacity: '0',
          },
          '100%': {
            transform: 'translateY(0)',
            opacity: '1',
          },
        },
        'slide-down': {
          '0%': {
            transform: 'translateY(0)',
            opacity: '1',
          },
          '100%': {
            transform: 'translateY(20px)',
            opacity: '0',
          },
        },
        'slide-left': {
          '0%': {
            transform: 'translateX(50px)',
            opacity: '0',
          },
          '100%': {
            transform: 'translateX(0)',
            opacity: '1',
          },
        },
        'slide-right': {
          '0%': {
            transform: 'translateX(0)',
            opacity: '1',
          },
          '100%': {
            transform: 'translateX(50px)',
            opacity: '0',
          },
        },
        'rotate-in': {
          '0%': {
            transform: 'rotateY(-90deg)',
            opacity: '0',
            transformOrigin: 'center',
          },
          '100%': {
            transform: 'rotateY(0)',
            opacity: '1',
            transformOrigin: 'center',
          },
        },
        'rotate-out': {
          '0%': {
            transform: 'rotateY(0)',
            opacity: '1',
            transformOrigin: 'center',
          },
          '100%': {
            transform: 'rotateY(90deg)',
            opacity: '0',
            transformOrigin: 'center',
          },
        },
      },
      animation: {
        pulse: 'pulseAnimation 3s infinite',
        greenPulse: 'greenPulseAnimation 3s infinite',
        redPulse: 'redPulseAnimation 3s infinite',
        orangePulse: 'orangePulseAnimation 3s infinite',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-in': 'fade-in 0.3s ease-out',
        'fade-out': 'fade-out 0.3s ease-out',
        'slide-in': 'slide-in 0.3s ease-out',
        'slide-out': 'slide-out 0.3s ease-out',
        'telegram-shake': 'telegram-shake 0.5s ease-in-out',
        'bounce-in': 'bounce-in 0.4s ease-out',
        'zoom-out': 'zoom-out 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'zoom-in': 'zoom-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'slide-up': 'slide-up 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'slide-down': 'slide-down 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'slide-left': 'slide-left 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'slide-right': 'slide-right 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'rotate-in': 'rotate-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'rotate-out': 'rotate-out 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
