import localFont from "next/font/local";

const hafferSans = localFont({
  src: "../app/fonts/HafferCollectionVF-TRIAL.ttf",
  display: "swap",
  variable: "--font-haffer-sans",
});

const hafferMono = localFont({
  src: [
    {
      path: "../app/fonts/HafferMono-TRIAL-Regular.otf",
      weight: "400",
      style: "normal",
    },
    {
      path: "../app/fonts/HafferMono-TRIAL-Medium.otf",
      weight: "500",
      style: "normal",
    },
    {
      path: "../app/fonts/HafferMono-TRIAL-SemiBold.otf",
      weight: "600",
      style: "normal",
    },
    {
      path: "../app/fonts/HafferMono-TRIAL-Bold.otf",
      weight: "700",
      style: "normal",
    },
  ],
  display: "swap",
  variable: "--font-haffer-mono",
});

export { hafferSans, hafferMono };
