import { Search, Filter, MapPin, Clock, ShieldCheck, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { PageWrapper, EmptyState } from "../components/ui/States";

export function Hire() {
  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4 lg:py-20 lg:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Hero Section */}
        <div className="mb-12 max-w-3xl">
          <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-plum">Find Local Help</p>
          <h1 className="text-4xl font-black leading-[1.05] tracking-tight text-ink lg:text-5xl">
            Hire trusted workers <span className="text-plum">near you</span>
          </h1>
          <p className="mt-4 max-w-xl text-lg leading-7 text-ink/60">
            Describe what you need, set your location, and browse available workers who match your requirements.
          </p>
        </div>

        {/* Search & Filter Bar */}
        <Card className="mb-8 p-6 bg-white">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
              <Input
                placeholder="What do you need help with? (e.g., furniture assembly, cleaning)"
                className="pl-10"
              />
            </div>
            <div className="relative flex-1 max-w-xs">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
              <Input
                placeholder="Your locality or area"
                className="pl-10"
              />
            </div>
            <Button className="w-full sm:w-auto gap-2">
              <Search size={16} />
              Search Workers
            </Button>
          </div>

          {/* Filter Toggle */}
          <div className="mt-4 pt-4 border-t border-ink/10 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3 text-sm text-ink/60">
              <Filter className="h-4 w-4 text-ink/40" />
              <span>Filters</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {["All", "Assembly", "Cleaning", "Gardening", "Moving", "Repairs"].map((category) => (
                <button
                  key={category}
                  className="px-3 py-1.5 text-xs font-medium rounded-full bg-ink/5 text-ink/60 hover:bg-ink/10 transition-colors"
                >
                  {category}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {/* Results Section */}
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-ink">Available Workers</h2>
            <div className="flex items-center gap-2 text-sm text-ink/60">
              <ShieldCheck className="h-4 w-4 text-plum" />
              <span>12 workers found</span>
            </div>
          </div>

          {/* Empty State for Workers - showing structure */}
          <EmptyState
            icon={<ShieldCheck size={32} />}
            title="No workers match your criteria yet"
            description="Workers matching your search will appear here. Each card shows their profile, skills, rating, and availability."
            action={{
              label: "Adjust Filters",
              variant: "secondary",
              onClick: () => {},
            }}
          />

          {/* Example Worker Card Structure (commented - will be real data) */}
          {/*
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              { name: "Rajesh Kumar", skills: ["Furniture Assembly", "IKEA Expert"], rating: 4.9, reviews: 127, distance: "2.3 km", hourly: "₹350" },
              { name: "Priya Sharma", skills: ["Deep Cleaning", "Eco-friendly"], rating: 4.8, reviews: 89, distance: "1.8 km", hourly: "₹280" },
              { name: "Amit Patel", skills: ["Garden Maintenance", "Landscaping"], rating: 4.7, reviews: 56, distance: "3.1 km", hourly: "₹300" },
            ].map((worker, idx) => (
              <Card key={idx} className="p-4 hover:border-plum/30 transition-colors">
                <div className="flex items-start gap-4">
                  <div className="h-16 w-16 rounded-full bg-plum/10 flex items-center justify-center flex-shrink-0">
                    <span className="text-xl font-bold text-plum">{worker.name.split(' ').map(n => n[0]).join('')}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-ink truncate">{worker.name}</h3>
                      <span className="px-2 py-1 text-xs rounded-full bg-emerald-50 text-emerald-700 font-medium">
                        {worker.rating} ★ ({worker.reviews})
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {worker.skills.map((skill, i) => (
                        <span key={i} className="px-2 py-1 text-xs rounded bg-plum/10 text-plum">{skill}</span>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center gap-4 text-sm text-ink/60">
                      <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {worker.distance}</span>
                      <span className="font-medium text-plum">{worker.hourly}/hr</span>
                    </div>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-ink/10">
                  <Button className="w-full gap-2" variant="outline">
                    <ArrowRight size={14} />
                    View Profile & Hire
                  </Button>
                </div>
              </Card>
            ))}}
          </div>
          */}
        </div>

        {/* Trust Indicators */}
        <Card className="mt-12 bg-plum/5 border-plum/20 p-6">
          <h3 className="text-lg font-bold text-plum mb-4">Why hire through SAHAKAR–SEVA?</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { icon: ShieldCheck, title: "Verified Workers", desc: "All workers complete profile verification before appearing in search" },
              { icon: Clock, title: "Transparent Pricing", desc: "Upfront hourly rates with no hidden fees or surprise charges" },
              { icon: ShieldCheck, title: "Fair Dispute Resolution", desc: "Built-in mediation for any disagreements — no one-sided black boxes" },
            ].map(({ icon: Icon, title, desc }, idx) => (
              <div key={idx} className="flex gap-3">
                <div className="h-10 w-10 rounded-lg bg-plum/20 flex items-center justify-center flex-shrink-0">
                  <Icon className="h-5 w-5 text-plum" />
                </div>
                <div>
                  <h4 className="font-semibold text-ink">{title}</h4>
                  <p className="text-sm text-ink/60">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </PageWrapper>
  );
}