import { Search, Briefcase, Filter, MapPin, Clock, ShieldCheck, ArrowRight, Star } from "lucide-react";
import { Link } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { PageWrapper, EmptyState } from "../components/ui/States";

export function FindWork() {
  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4 lg:py-20 lg:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Hero Section */}
        <div className="mb-12 max-w-3xl">
          <p className="mb-4 text-sm font-bold uppercase tracking-[0.2em] text-plum">Find Local Work</p>
          <h1 className="text-4xl font-black leading-[1.05] tracking-tight text-ink lg:text-5xl">
            Discover jobs <span className="text-plum">near you</span>
          </h1>
          <p className="mt-4 max-w-xl text-lg leading-7 text-ink/60">
            Browse local job postings, filter by your skills and availability, and apply directly to opportunities that match your expertise.
          </p>
        </div>

        {/* Search & Filter Bar */}
        <Card className="mb-8 p-6 bg-white">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
              <Input
                placeholder="What work are you looking for? (e.g., assembly, cleaning)"
                className="pl-10"
              />
            </div>
            <div className="relative flex-1 max-w-xs">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
              <Input
                placeholder="Your area or max travel distance"
                className="pl-10"
              />
            </div>
            <Button className="w-full sm:w-auto gap-2">
              <Search size={16} />
              Find Jobs
            </Button>
          </div>

          {/* Filter Toggle */}
          <div className="mt-4 pt-4 border-t border-ink/10 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3 text-sm text-ink/60">
              <Filter className="h-4 w-4 text-ink/40" />
              <span>Filters</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {["All", "Assembly", "Cleaning", "Gardening", "Moving", "Repairs", "Painting", "Plumbing"].map((category) => (
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
            <h2 className="text-xl font-bold text-ink">Available Jobs</h2>
            <div className="flex items-center gap-2 text-sm text-ink/60">
              <Filter className="h-4 w-4 text-ink/40" />
              <span>24 jobs posted this week</span>
            </div>
          </div>

          {/* Empty State for Jobs - showing structure */}
          <EmptyState
            icon={<Briefcase size={32} />}
            title="No jobs match your criteria yet"
            description="Job postings matching your skills and location will appear here. Each card shows the task details, budget, location, and required skills."
            action={{
              label: "Adjust Filters",
              variant: "secondary",
              onClick: () => {},
            }}
          />

          {/* Example Job Card Structure (commented - will be real data) */}
          {/*
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              { title: "Furniture Assembly - IKEA PAX Wardrobe", category: "Assembly", budget: "₹1,200", duration: "3-4 hrs", location: "Koramangala, 2.1 km", posted: "2 hrs ago", skills: ["IKEA", "Furniture", "Tools provided"] },
              { title: "Weekly Apartment Cleaning", category: "Cleaning", budget: "₹800", duration: "2 hrs", location: "Indiranagar, 1.5 km", posted: "5 hrs ago", skills: ["Cleaning", "Eco-friendly products"] },
              { title: "Garden Maintenance & Weeding", category: "Gardening", budget: "₹600", duration: "2 hrs", location: "Whitefield, 3.2 km", posted: "1 day ago", skills: ["Gardening", "Weeding", "Tools provided"] },
              { title: "Moving Help - 2BR Apartment", category: "Moving", budget: "₹2,500", duration: "4-5 hrs", location: "HSR Layout, 4.0 km", posted: "3 hrs ago", skills: ["Lifting", "Packing", "Van provided"] },
              { title: "Wall Patch & Paint Touch-up", category: "Repairs", budget: "₹1,500", duration: "3 hrs", location: "Jayanagar, 2.8 km", posted: "6 hrs ago", skills: ["Painting", "Drywall", "Prep work"] },
              { title: "Kitchen Deep Clean", category: "Cleaning", budget: "₹1,000", duration: "3 hrs", location: "Bellandur, 2.5 km", posted: "1 day ago", skills: ["Deep cleaning", "Degreasing", "Appliance clean"] },
            ].map((job, idx) => (
              <Card key={idx} className="p-4 hover:border-plum/30 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <span className="px-2 py-1 text-xs rounded-full bg-plum/10 text-plum font-medium">{job.category}</span>
                  <span className="text-xs text-ink/50">{job.posted}</span>
                </div>
                <h3 className="font-semibold text-ink mb-2 line-clamp-1">{job.title}</h3>
                <div className="flex flex-wrap gap-2 mb-3">
                  {job.skills.map((skill, i) => (
                    <span key={i} className="px-2 py-1 text-xs rounded bg-ink/5 text-ink/60">{skill}</span>
                  ))}
                </div>
                <div className="flex items-center gap-4 text-sm text-ink/60 mb-4">
                  <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> {job.location}</span>
                  <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {job.duration}</span>
                </div>
                <div className="flex items-center justify-between pt-3 border-t border-ink/10">
                  <span className="text-lg font-bold text-plum">{job.budget}</span>
                  <div className="flex items-center gap-2">
                    <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
                    <span className="text-sm font-medium">4.7 avg rating</span>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-ink/10">
                  <Button className="w-full gap-2" variant="primary">
                    <ArrowRight size={14} />
                    View Details & Apply
                  </Button>
                </div>
              </Card>
            ))}}
          </div>
          */}
        </div>

        {/* Worker Benefits */}
        <Card className="mt-12 bg-plum/5 border-plum/20 p-6">
          <h3 className="text-lg font-bold text-plum mb-4">Why find work through SAHAKAR–SEVA?</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { icon: ShieldCheck, title: "Fair Pay Transparency", desc: "See exact pay before applying — no hidden platform fees deducted from your earnings" },
              { icon: Clock, title: "Flexible Schedule", desc: "Choose jobs that fit your availability — morning, evening, or weekends" },
              { icon: Star, title: "Build Your Reputation", desc: "Earn ratings and reviews that help you get more and better jobs over time" },
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