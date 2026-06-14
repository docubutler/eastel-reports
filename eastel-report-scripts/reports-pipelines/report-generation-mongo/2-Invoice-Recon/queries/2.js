/*
Query 2:
Count SMS records by rating group according to config date

Output:
{
  count: 967787,
  rating_group: 'SM'
}
*/



db.usage_logs.aggregate([
  {
    $match: {
      rat_type: "SM",
      usage_start_time: {
        $gte: ISODate(${start_date}),
        $lt: ISODate(${end_date})
      }
    }
  },
  {
    $group: {
      _id: "$rating_group",
      count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      rating_group: "$_id",
      count: 1
    }
  },
  {
    $sort: {
      rating_group: 1
    }
  }
]);