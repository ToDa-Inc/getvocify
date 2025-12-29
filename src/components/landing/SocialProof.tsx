const companies = [
  "TechCorp", "SalesForce", "GrowthCo", "ScaleUp", "CloseDeal", "WinMore"
];

const SocialProof = () => {
  return (
    <section className="py-20 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <p className="text-center text-sm font-medium text-muted-foreground mb-10 uppercase tracking-wider">
          Trusted by modern sales teams
        </p>

        {/* Company logos */}
        <div className="flex flex-wrap justify-center items-center gap-8 md:gap-12 mb-16 opacity-50">
          {companies.map((company) => (
            <div
              key={company}
              className="text-xl md:text-2xl font-bold text-muted-foreground/60 hover:text-muted-foreground transition-colors"
            >
              {company}
            </div>
          ))}
        </div>

        {/* Testimonial */}
        <div className="max-w-3xl mx-auto text-center">
          <blockquote className="text-xl md:text-2xl font-medium text-foreground leading-relaxed mb-6">
            "Vocify saves me 6 hours every week. I update my pipeline while driving between meetings."
          </blockquote>
          <div className="flex items-center justify-center gap-3">
            <div className="w-12 h-12 rounded-full bg-beige/20 flex items-center justify-center">
              <span className="text-lg font-semibold text-beige">MR</span>
            </div>
            <div className="text-left">
              <p className="font-semibold text-foreground">Michael Roberts</p>
              <p className="text-sm text-muted-foreground">VP of Sales, TechCorp</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default SocialProof;
