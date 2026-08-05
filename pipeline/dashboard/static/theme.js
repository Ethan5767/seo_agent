// Extracted once from the Stitch export; every page loads this instead of
// carrying its own copy. Edit the palette here.
tailwind.config = {
        darkMode: "class",
        theme: {
          extend: {
            "colors": {
                    "on-secondary-fixed": "#0d1c2d",
                    "primary": "#8ed5ff",
                    "on-surface-variant": "#bdc8d1",
                    "surface-container-high": "#222a3d",
                    "tertiary-container": "#f1a02b",
                    "surface": "#0b1326",
                    "tertiary": "#ffc176",
                    "primary-fixed": "#c4e7ff",
                    "on-primary": "#00354a",
                    "on-tertiary": "#472a00",
                    "secondary-container": "#39485a",
                    "outline": "#87929a",
                    "on-primary-container": "#004965",
                    "on-tertiary-container": "#613b00",
                    "inverse-on-surface": "#283044",
                    "secondary-fixed-dim": "#b9c8de",
                    "surface-dim": "#0b1326",
                    "error": "#ffb4ab",
                    "on-secondary-fixed-variant": "#39485a",
                    "inverse-primary": "#00668a",
                    "primary-container": "#38bdf8",
                    "surface-container-highest": "#2d3449",
                    "surface-variant": "#2d3449",
                    "secondary": "#b9c8de",
                    "on-error": "#690005",
                    "surface-tint": "#7bd0ff",
                    "tertiary-fixed-dim": "#ffb960",
                    "on-secondary": "#233143",
                    "secondary-fixed": "#d4e4fa",
                    "on-secondary-container": "#a7b6cc",
                    "outline-variant": "#3e484f",
                    "tertiary-fixed": "#ffddb8",
                    "on-tertiary-fixed": "#2a1700",
                    "primary-fixed-dim": "#7bd0ff",
                    "error-container": "#93000a",
                    "on-background": "#dae2fd",
                    "surface-container-low": "#131b2e",
                    "surface-container-lowest": "#060e20",
                    "on-surface": "#dae2fd",
                    "surface-bright": "#31394d",
                    "on-primary-fixed": "#001e2c",
                    "on-tertiary-fixed-variant": "#653e00",
                    "on-error-container": "#ffdad6",
                    "on-primary-fixed-variant": "#004c69",
                    "background": "#0b1326",
                    "surface-container": "#171f33",
                    "inverse-surface": "#dae2fd"
            },
            "borderRadius": {
                    "DEFAULT": "0.125rem",
                    "lg": "0.25rem",
                    "xl": "0.5rem",
                    "full": "0.75rem"
            },
            "spacing": {
                    "md": "16px",
                    "xl": "32px",
                    "gutter": "1px",
                    "panel-padding": "12px",
                    "sm": "8px",
                    "xs": "4px",
                    "unit": "4px",
                    "lg": "24px"
            },
            "fontFamily": {
                    "body-sm": [
                            "Inter"
                    ],
                    "headline-sm": [
                            "Inter"
                    ],
                    "body-md": [
                            "Inter"
                    ],
                    "label-caps": [
                            "Inter"
                    ],
                    "mono-sm": [
                            "JetBrains Mono"
                    ],
                    "mono-base": [
                            "JetBrains Mono"
                    ]
            },
            "fontSize": {
                    "body-sm": [
                            "12px",
                            {
                                    "lineHeight": "16px",
                                    "fontWeight": "400"
                            }
                    ],
                    "headline-sm": [
                            "18px",
                            {
                                    "lineHeight": "24px",
                                    "letterSpacing": "-0.01em",
                                    "fontWeight": "600"
                            }
                    ],
                    "body-md": [
                            "14px",
                            {
                                    "lineHeight": "20px",
                                    "fontWeight": "400"
                            }
                    ],
                    "label-caps": [
                            "11px",
                            {
                                    "lineHeight": "12px",
                                    "letterSpacing": "0.05em",
                                    "fontWeight": "700"
                            }
                    ],
                    "mono-sm": [
                            "11px",
                            {
                                    "lineHeight": "14px",
                                    "letterSpacing": "0.02em",
                                    "fontWeight": "500"
                            }
                    ],
                    "mono-base": [
                            "13px",
                            {
                                    "lineHeight": "18px",
                                    "fontWeight": "400"
                            }
                    ]
            }
    },
        },
      }
