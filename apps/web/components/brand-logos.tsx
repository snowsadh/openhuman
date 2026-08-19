import React from "react";
import {
  SiGithub,
  SiGmail,
  SiNotion,
  SiVercel,
  SiBrave,
  SiPostgresql,
  SiStripe,
  SiAirtable,
  SiSnowflake,
  SiWikipedia,
  SiYoutube,
  SiRedis,
  SiDocker,
  SiGitlab,
  SiFigma,
  SiHubspot,
  SiZendesk,
  SiTrello,
  SiGooglecalendar,
  SiMedium,
  SiDiscord,
  SiGooglemaps,
  SiZoom,
  SiClickup,
  SiFirebase,
  SiElasticsearch,
  SiHuggingface,
  SiJira,
  SiLinear,
  SiShopify,
  SiCanvas,
} from "react-icons/si";
import { FaAws, FaSalesforce, FaSlack } from "react-icons/fa6";

// Custom SVG Logos for cases where simple-icons is missing or we want full-color multi-color SVGs

// Multi-color Gmail Logo
export const GmailLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M20 4H4C2.9 4 2 4.9 2 6V18C2 19.1 2.9 20 4 20H20C21.1 20 22 19.1 22 18V6C22 4.9 21.1 4 20 4Z" fill="#ea4335" />
    <path d="M22 6V18C22 19.1 21.1 20 20 20H17V8L12 12L7 8V20H4C2.9 20 2 19.1 2 18V6C2 4.9 2.9 4 4 4H20C21.1 4 22 4.9 22 6Z" fill="#4285f4" />
    <path d="M2 18V6C2 4.9 2.9 4 4 4H7V20H4C2.9 20 2 19.1 2 18Z" fill="#34a853" />
    <path d="M22 6V18C22 19.1 21.1 20 20 20H17V4H20C21.1 4 22 4.9 22 6Z" fill="#fbbc05" />
  </svg>
);

// Multi-color Slack Logo
export const SlackLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <g fill="currentColor">
      {/* Top blob - Blue */}
      <path d="M5.04 15.12a2.52 2.52 0 1 1-2.52-2.52h2.52v2.52zm1.26 0a2.52 2.52 0 0 1 5.04 0v5.04a2.52 2.52 0 1 1-5.04 0v-5.04z" fill="#36C5F0" />
      {/* Right blob - Green */}
      <path d="M8.88 5.04a2.52 2.52 0 1 1 2.52-2.52v2.52H8.88zm0 1.26a2.52 2.52 0 0 1 0 5.04H3.84a2.52 2.52 0 1 1 0-5.04h5.04z" fill="#2EB67D" />
      {/* Bottom blob - Yellow */}
      <path d="M18.96 8.88a2.52 2.52 0 1 1 2.52 2.52h-2.52V8.88zm-1.26 0a2.52 2.52 0 0 1-5.04 0V3.84a2.52 2.52 0 1 1 5.04 0v5.04z" fill="#ECB22E" />
      {/* Left blob - Red */}
      <path d="M15.12 18.96a2.52 2.52 0 1 1-2.52 2.52v-2.52h2.52zm0-1.26a2.52 2.52 0 0 1 0-5.04h5.04a2.52 2.52 0 1 1 0 5.04h-5.04z" fill="#E01E5A" />
    </g>
  </svg>
);

// Gamma leaf logo custom SVG
export const GammaLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM11.5 17C9.01 17 7 14.99 7 12.5C7 10.01 9.01 8 11.5 8C13.99 8 16 10.01 16 12.5C16 14.99 13.99 17 11.5 17Z" fill="url(#gamma-logo-grad)" />
    <defs>
      <linearGradient id="gamma-logo-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
        <stop stopColor="#EC4899" />
        <stop offset="0.5" stopColor="#A855F7" />
        <stop offset="1" stopColor="#6366F1" />
      </linearGradient>
    </defs>
  </svg>
);

// Pitch Deck Generator — simple presentation/slides icon
export const PitchDeckLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <rect x="2" y="4" width="20" height="13" rx="2" fill="#F97316" />
    <rect x="4.5" y="6.5" width="8" height="1.6" rx="0.8" fill="white" fillOpacity="0.9" />
    <rect x="4.5" y="9.2" width="12" height="1.4" rx="0.7" fill="white" fillOpacity="0.7" />
    <rect x="4.5" y="11.6" width="10" height="1.4" rx="0.7" fill="white" fillOpacity="0.7" />
    <path d="M9 20L12 17L15 20" stroke="#F97316" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// n8n logo-inspired connected nodes mark
export const N8nLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M8 8L12 12M12 12L8 16M12 12H16" stroke="#EA4B71" strokeWidth="2" strokeLinecap="round" />
    <circle cx="8" cy="8" r="3" fill="#FF6D5A" />
    <circle cx="8" cy="16" r="3" fill="#FF4F64" />
    <circle cx="16" cy="12" r="3" fill="#D63CF0" />
  </svg>
);

// Twilio Logo custom SVG
export const TwilioLogo = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2ZM7.5 13.5C6.67 13.5 6 12.83 6 12C6 11.17 6.67 10.5 7.5 10.5C8.33 10.5 9 11.17 9 12C9 12.83 8.33 13.5 7.5 13.5ZM10.5 16.5C9.67 16.5 9 15.83 9 15C9 14.17 9.67 13.5 10.5 13.5C11.33 13.5 12 14.17 12 15C12 15.83 11.33 16.5 10.5 16.5ZM10.5 10.5C9.67 10.5 9 9.83 9 9C9 8.17 9.67 7.5 10.5 7.5C11.33 7.5 12 8.17 12 9C12 9.83 11.33 10.5 10.5 10.5ZM13.5 13.5C12.67 13.5 12 12.83 12 12C12 11.17 12.67 10.5 13.5 10.5C14.33 10.5 15 11.17 15 12C15 12.83 14.33 13.5 13.5 13.5Z" fill="#F22F46" />
  </svg>
);

// Map of Brand SVG components by connector slug or marketplace server ID
export const BRAND_LOGOS: Record<string, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  gmail: GmailLogo,
  github: (props) => <SiGithub fill="currentColor" className="text-zinc-900 dark:text-white" {...props} />,
  notion: (props) => <SiNotion fill="currentColor" className="text-black dark:text-white" {...props} />,
  vercel: (props) => <SiVercel fill="currentColor" className="text-black dark:text-white" {...props} />,
  gamma: GammaLogo,
  n8n: N8nLogo,
  canva: (props) => <SiCanvas fill="#00C4CC" {...props} />,
  pitchdeck: PitchDeckLogo,
  slack: SlackLogo,
  postgres: (props) => <SiPostgresql fill="#4169E1" {...props} />,
  "brave-search": (props) => <SiBrave fill="#FF1B2D" {...props} />,
  web_search: (props) => <SiBrave fill="#FF1B2D" {...props} />,
  huggingface: (props) => <SiHuggingface fill="#FFD21E" {...props} />,
  jira: (props) => <SiJira fill="#0052CC" {...props} />,
  linear: (props) => <SiLinear fill="currentColor" className="text-black dark:text-white" {...props} />,
  shopify: (props) => <SiShopify fill="#96BF48" {...props} />,
  stripe: (props) => <SiStripe fill="#008CDD" {...props} />,
  airtable: (props) => <SiAirtable fill="#18BFFF" {...props} />,
  snowflake: (props) => <SiSnowflake fill="#29B5E8" {...props} />,
  wikipedia: (props) => <SiWikipedia fill="currentColor" className="text-zinc-600 dark:text-zinc-300" {...props} />,
  youtube: (props) => <SiYoutube fill="#FF0000" {...props} />,
  redis: (props) => <SiRedis fill="#DC382D" {...props} />,
  docker: (props) => <SiDocker fill="#2496ED" {...props} />,
  "aws-s3": (props) => <FaAws fill="#FF9900" {...props} />,
  gitlab: (props) => <SiGitlab fill="#FC6D26" {...props} />,
  figma: (props) => <SiFigma fill="#F24E1E" {...props} />,
  salesforce: (props) => <FaSalesforce fill="#00A1E0" {...props} />,
  hubspot: (props) => <SiHubspot fill="#FF7A59" {...props} />,
  zendesk: (props) => <SiZendesk fill="#03363D" {...props} />,
  trello: (props) => <SiTrello fill="#0079BF" {...props} />,
  "google-calendar": (props) => <SiGooglecalendar fill="#4285F4" {...props} />,
  twilio: TwilioLogo,
  medium: (props) => <SiMedium fill="currentColor" className="text-black dark:text-white" {...props} />,
  discord: (props) => <SiDiscord fill="#5865F2" {...props} />,
  "google-maps": (props) => <SiGooglemaps fill="#EA4335" {...props} />,
  zoom: (props) => <SiZoom fill="#2D8CFF" {...props} />,
  clickup: (props) => <SiClickup fill="#7B68EE" {...props} />,
  firebase: (props) => <SiFirebase fill="#FFCA28" {...props} />,
  "exa-search": (props) => <svg viewBox="0 0 24 24" fill="currentColor" {...props}><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" fill="#10B981"/></svg>,
  elasticsearch: (props) => <SiElasticsearch fill="#005571" {...props} />,
};

interface BrandLogoProps extends React.SVGProps<SVGSVGElement> {
  slug: string;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({ slug, ...props }) => {
  const LogoComponent = BRAND_LOGOS[slug];
  if (!LogoComponent) {
    // Default fallback simple circle icon if slug doesn't exist
    return (
      <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
        <circle cx="12" cy="12" r="10" fill="#CBD5E1" />
      </svg>
    );
  }
  return <LogoComponent {...props} />;
};
