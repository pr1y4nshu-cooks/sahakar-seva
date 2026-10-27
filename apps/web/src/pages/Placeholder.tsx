import { Construction } from "lucide-react";
import { Card } from "../components/ui/Card";

export function Placeholder({ title, description }: { title: string; description: string }) {
  return <div className="mx-auto max-w-6xl px-5 py-16 lg:px-8"><Card className="mx-auto max-w-2xl text-center"><Construction className="mx-auto mb-6 text-plum" size={30} /><p className="text-sm font-bold uppercase tracking-[0.2em] text-plum">Coming in a future phase</p><h1 className="mt-4 text-4xl font-black tracking-tight">{title}</h1><p className="mx-auto mt-5 max-w-lg leading-7 text-ink/60">{description}</p></Card></div>;
}

