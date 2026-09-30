# Research & Design Tokens Summary

## Institutional Banking Research Findings (Citi & NPCI)

### 1. Color Palette Tokens
- **Primary Institutional Blue (Citi style)**: `#0047BA` (RGB: 0, 71, 186) / `#056DAE`
- **Dark Header / Utility Strip Navy (NPCI / Citi fusion)**: `#19191C` / `#001737`
- **Secondary / Accent Colors**:
  - Orange/Amber Highlight (NPCI accent): `#FF9029`
  - Deep Navy Text / Header: `#0F172A` / `#1E293B`
- **Backgrounds**:
  - Main Page Background: `#F8FAFC` (Light institutional slate grey)
  - Card / Surface Background: `#FFFFFF`
  - Header Utility Strip Background: `#18181B` / `#001737`
  - Footer Background: `#0F172A` / `#19191C`
- **Borders**:
  - Standard Surface Border: `1px solid #E2E8F0` / `#D1D5DB`
  - Input Border: `1px solid #CBD5E1`
  - Table Hairline Border: `1px solid #E2E8F0`

### 2. Typography & Type Scale
- **Font Family Stack**: `Archivo`, "Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif
- **Type Scale**:
  - Page Title (H1): 24px - 28px, Weight: 700, Line-height: 1.25, Color: `#0F172A`
  - Section Header (H2): 18px - 20px, Weight: 600, Line-height: 1.3, Color: `#1E293B`
  - Subtitle / Card Title (H3): 15px - 16px, Weight: 600, Line-height: 1.4, Color: `#334155`
  - Body Text: 14px - 15px, Weight: 400, Line-height: 1.5, Color: `#334155`
  - Table & Data Text: 13px - 14px, Weight: 400, Line-height: 1.4, Color: `#334155`
  - Labels & Helper Text: 12px - 13px, Weight: 600 (Labels) / 400 (Helper), Color: `#475569` / `#64748B`
  - Utility Strip Text: 12px, Weight: 400, Color: `#A1A1A2` / `#CBD5E1`

### 3. Component Styles & Controls
- **Buttons (Rectangular Institutional Style)**:
  - Height: 38px - 40px
  - Padding: 8px 16px to 10px 20px
  - Border Radius: 2px - 4px (Strictly rectangular, non-pill)
  - Primary Button: Background `#0047BA`, Color `#FFFFFF`, Font-weight 600, Border `1px solid #0047BA`
  - Secondary Button: Background `#FFFFFF`, Color `#0047BA`, Font-weight 600, Border `1px solid #CBD5E1`
- **Form Inputs & Selects**:
  - Height: 38px
  - Padding: 8px 12px
  - Border Radius: 2px - 4px
  - Border: `1px solid #CBD5E1`
  - Focus Ring: `2px solid #0047BA`, outline none
  - Validation / Helper text: 12px below input, `#DC2626` for error, `#64748B` for help
- **Tables**:
  - Table Header: Background `#F8FAFC`, Color `#334155`, Font-weight 600, 12px uppercase or 13px bold, border bottom `2px solid #E2E8F0`
  - Table Rows: Height 44px - 48px, 1px bottom border `#F1F5F9`, alternating light zebra `#FAFAFA`
- **Badges / Status Indicators**:
  - Rectangular badges with 2px radius (not pill)
  - Padding: 2px 8px, Font size: 12px, Weight: 600
  - Success (COMPLETED / APPROVED): Background `#F0FDF4`, Text `#15803D`, Border `1px solid #BBF7D0`
  - Warning / Hold (HELD / PENDING): Background `#FEF3C7`, Text `#B45309`, Border `1px solid #FDE68A`
  - Error / Failure (FAILED / REJECTED): Background `#FEE2E2`, Text `#B91C1C`, Border `1px solid #FCA5A5`

### 4. Structural Layout Rules
- **Container Max-Width**: 1160px - 1200px centered
- **Grid Rhythm**: 8px spacing system (8px, 16px, 24px, 32px, 48px)
- **Top Utility Strip**: 36px height, dark background `#18181B`, language dropdown, Help links, Prototype tag
- **Main Header**: 64px height, white background, bottom border `1px solid #E2E8F0`, logo "RemitChain", horizontal nav tabs
- **Breadcrumb**: 32px height bar below header, 12px text size, `#64748B`
- **Footer**: Multi-column institutional layout, dark background `#0F172A`, legal disclaimer, Drunix backend status

### 5. Institutional Feel Rationale
What makes this feel like a real institutional banking portal rather than an AI dashboard:
1. **Flat, Crisp Surfaces**: No glassmorphism, background blurs, decorative gradients, or floating cards with heavy soft shadows.
2. **Dense Data Presentation**: Form fields with top-aligned explicit labels, helper text, inline errors, strict 13-14px table rows with sortable headers and crisp status badges.
3. **Rectangular Controls**: 2-4px radius buttons and inputs; zero rounded pill buttons or floating floating action buttons.
4. **Structured Information Architecture**: Top utility bar -> Header navigation bar -> Breadcrumbs -> Main content container -> Formal footer with regulatory disclaimers.
5. **Strict Tone & Copy**: Professional banking terms ("Beneficiary Account", "Remitting Institution", "FX Conversion Rate", "Regulatory Verification") with clean semantic status tags.
